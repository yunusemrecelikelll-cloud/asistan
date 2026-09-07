import Foundation
import NovaPaylasilan
import WatchConnectivity

/// Saatin TEK yolu: telefon üzerinden.
///
/// Saat hiçbir ayar tutmuyor — sunucu adresi de parola da yok. Yaptığı tek
/// iş konuşmayı telefona vermek ve telefondan gelen sesi çalmak. Bilgisayara
/// ulaşmayı, kimlik doğrulamayı, Tailscale'i telefon halediyor.
///
/// Doğrudan Wi-Fi yolu bilerek yok: saatte adres/parola girecek bir ekran
/// olmayınca o yol zaten hiç kurulamıyordu, ama denenmesi her bağlanışa
/// 1,2 saniye bindiriyordu. Tek yol bırakınca hem kod hem gecikme azaldı.
///
/// ## Kablo üzerindeki biçim
///
/// `WCSession.sendMessage` tek mesajda ~64 KB taşıyabiliyor ve bu bağ
/// Bluetooth — yani asıl darboğaz bant genişliği. Bu yüzden:
///
///   * Telefon sesi **AAC'ye sıkıştırıp** yolluyor (96 KB → ~8 KB).
///   * Yine de sığmayan olursa dilimlere bölünüyor; dilimler burada
///     birleştiriliyor.
///   * Bir ses parçasını tarif eden başlık ile verisi **aynı mesajda**
///     gidiyor. Eskiden iki ayrı mesajdı ve sıraları karışabiliyordu.
///
/// Mikrofon ham PCM olarak gidiyor (sıkıştırma konuşma tanımanın isabetini
/// düşürür); küçük tamponlar 4 KB'lık paketlerde birleştirilip yollanıyor —
/// saniyede 23 mesaj yerine 8.
final class RoleTasiyici: NSObject, Tasiyici {

    var metinGeldi: ((Data) -> Void)?
    var ikiliGeldi: ((Data) -> Void)?
    var durumDegisti: ((TasiyiciDurumu) -> Void)?

    let ad = "telefon üzerinden"

    /// Kimlik ve nabız telefonun işi; saat ikisini de yapmıyor.
    let sunucuyaDogrudan = false

    /// Giden mikrofon verisi bu boyuta ulaşınca yollanıyor. 4 KB, 16 kHz
    /// mono PCM'de 125 ms demek — konuşma sürerken akıyor, sonda `yolla()`
    /// zaten kalanı boşaltıyor, yani tura gecikme eklemiyor.
    private let paketBoyu = 4 * 1024

    private var giden = Data()
    private let gidenKilit = NSLock()

    /// Gelen ses dilimlerinin toplandığı yer: parça kimliği → dilimler.
    private var toplananlar: [Int: [Int: Data]] = [:]
    private var toplananBicim: [Int: String] = [:]
    private let toplamaKilit = NSLock()
    /// Tarif çerçevesi ile onu izleyen ikili verinin arasına başka bir
    /// parça girmesin. İki parça aynı anda tamamlanırsa eşleşme bozulurdu.
    private let yayinKilit = NSLock()

    private var oturum: WCSession? {
        WCSession.isSupported() ? WCSession.default : nil
    }

    override init() {
        super.init()
        guard let o = oturum else { return }
        o.delegate = self
        o.activate()
    }

    // MARK: - Tasiyici

    func ac() {
        guard let o = oturum else {
            durumDegisti?(.hata("Saat-telefon bağlantısı yok"))
            return
        }
        guard o.isReachable else {
            durumDegisti?(.hata("Telefona ulaşılamıyor"))
            return
        }
        durumDegisti?(.acik)
        // Telefona "kanalı aç" de. Telefon zaten açıksa mevcut durumunu
        // yeniden yollayacak — yoksa saat sonsuza kadar "Bağlanıyor…"da
        // kalıyordu, çünkü `hazir` yalnızca durum değiştiğinde geliyor.
        gonder(["komut": "role_ac"])
    }

    func kapat() {
        bosalt()
        gonder(["komut": "role_kapat"])
        durumDegisti?(.kapali)
    }

    func yolla(_ veri: Data) {
        // Kontrol çerçevesinden ÖNCE biriken sesi boşalt: `ses_bitti`
        // mesajı, tarif ettiği sesin arkasından gitmeli.
        bosalt()
        gonder(["c": veri])
    }

    func ikiliYolla(_ veri: Data) {
        gidenKilit.lock()
        giden.append(veri)
        let hazir: Data?
        if giden.count >= paketBoyu {
            hazir = giden
            giden = Data()
        } else {
            hazir = nil
        }
        gidenKilit.unlock()
        if let hazir { gonder(["m": hazir]) }
    }

    /// Biriken mikrofon verisini hemen yolla.
    private func bosalt() {
        gidenKilit.lock()
        let kalan = giden
        giden = Data()
        gidenKilit.unlock()
        if !kalan.isEmpty { gonder(["m": kalan]) }
    }

    private func gonder(_ yuk: [String: Any]) {
        guard let o = oturum, o.isReachable else {
            durumDegisti?(.hata("Telefona ulaşılamıyor"))
            return
        }
        o.sendMessage(yuk, replyHandler: nil) { [weak self] hata in
            self?.durumDegisti?(.hata(hata.localizedDescription))
        }
    }

    // MARK: - Gelen sesin birleştirilmesi

    private func sesDilimi(_ m: [String: Any]) {
        guard let dilim = m["a"] as? Data,
              let kimlik = m["i"] as? Int,
              let sira = m["k"] as? Int,
              let toplam = m["n"] as? Int, toplam > 0 else { return }
        let bicim = m["b"] as? String ?? "audio/wav"

        var tam: Data?
        toplamaKilit.lock()
        toplananBicim[kimlik] = bicim
        var parcalar = toplananlar[kimlik] ?? [:]
        parcalar[sira] = dilim
        if parcalar.count == toplam {
            var birlesik = Data()
            for i in 0..<toplam {
                guard let p = parcalar[i] else { birlesik = Data(); break }
                birlesik.append(p)
            }
            tam = birlesik.isEmpty ? nil : birlesik
            toplananlar.removeValue(forKey: kimlik)
            toplananBicim.removeValue(forKey: kimlik)
        } else {
            toplananlar[kimlik] = parcalar
            // Yarım kalmış eski parçalar bellekte birikmesin.
            if toplananlar.count > 8, let enEski = toplananlar.keys.min() {
                toplananlar.removeValue(forKey: enEski)
                toplananBicim.removeValue(forKey: enEski)
            }
        }
        toplamaKilit.unlock()

        guard let tam else { return }
        // Protokolün beklediği sırayı burada üretiyoruz: önce parçayı tarif
        // eden JSON çerçevesi, hemen ardından ikili veri. Böylece
        // `NovaBaglanti` röleyi hiç bilmeden çalışmaya devam ediyor.
        let tarif: [String: Any] = ["tur": "parca", "sira": kimlik,
                                    "bayt": tam.count, "bicim": bicim,
                                    "metin": ""]
        yayinKilit.lock()
        if let d = try? JSONSerialization.data(withJSONObject: tarif) {
            metinGeldi?(d)
        }
        ikiliGeldi?(tam)
        yayinKilit.unlock()
    }
}

extension RoleTasiyici: WCSessionDelegate {

    func session(_ session: WCSession,
                 activationDidCompleteWith state: WCSessionActivationState,
                 error: Error?) {
        durumDegisti?(session.isReachable ? .acik
                      : .hata("Telefona ulaşılamıyor"))
        if session.isReachable { gonder(["komut": "role_ac"]) }
    }

    func sessionReachabilityDidChange(_ session: WCSession) {
        if session.isReachable {
            durumDegisti?(.acik)
            gonder(["komut": "role_ac"])
        } else {
            durumDegisti?(.hata("Telefona ulaşılamıyor"))
        }
    }

    func session(_ session: WCSession, didReceiveMessage m: [String: Any]) {
        if m["a"] != nil { sesDilimi(m); return }
        if let d = m["c"] as? Data { metinGeldi?(d) }
    }
}
