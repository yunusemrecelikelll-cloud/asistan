import Foundation
import NovaPaylasilan
import WatchConnectivity

/// Telefonun saat için yaptığı röle işi.
///
/// Saat hiçbir ayar tutmuyor ve bilgisayara hiç ulaşmıyor: konuşmayı buraya
/// yolluyor, telefon kendi bağlantısı (yerel ağ ya da Tailscale) üzerinden
/// bilgisayara geçiriyor, dönen sesi saate aktarıyor. Kimlik doğrulama da
/// burada — saatte parola yok.
///
/// ## Gecikme için ne yapılıyor
///
/// Saat ile telefon arasındaki bağ Bluetooth ve asıl darboğaz o. XTTS 24 kHz
/// WAV üretiyor: iki saniyelik bir cümle 96 KB, bu bağda yarım saniyeden
/// fazla aktarım. Sesi AAC'ye çevirip yolluyoruz — aynı cümle ~8 KB'a
/// iniyor, kodlama telefonda 10-20 ms. Saatte ilk sesin duyulma anı
/// doğrudan bu farka bağlı.
///
/// `sendMessage` tek mesajda ~64 KB taşıyor; sıkıştırmadan sonra çoğu parça
/// tek mesaja sığıyor, sığmayan dilimleniyor. Bir parçanın başlığı ile
/// verisi **aynı** mesajda gidiyor: eskiden iki ayrı mesajdı ve
/// `sendMessage` sıra garantisi vermediği için eşleşme bozulabiliyordu.
final class SaatRolesi: NSObject, ObservableObject {

    @Published private(set) var saatBagli = false
    @Published private(set) var roleAcik = false

    /// Röle için kullanılan AYRI bağlantı. Telefonun kendi oturumunu
    /// kullansaydık saat konuşurken telefon ekranındaki sohbet de
    /// karışırdı — ikisi bağımsız kalmalı.
    private var baglanti: NovaBaglanti?

    /// `sendMessage` yükü için güvenli üst sınır. Belgelenmiş sınır 64 KB;
    /// sözlük ve serileştirme payını bırakıyoruz.
    private let dilimBoyu = 40 * 1024

    private var sonrakiKimlik = 0

    /// Saatten gelen mesajlar arka planda ve BİRDEN ÇOK iş parçacığında
    /// gelebiliyor. Röleyi açma/kapama ve parça numaralandırma bunu
    /// kaldırmıyordu; hepsini tek seri kuyruğa alıyoruz.
    private let kuyruk = DispatchQueue(label: "nova.role")

    private var oturum: WCSession? {
        WCSession.isSupported() ? WCSession.default : nil
    }

    override init() {
        super.init()
        guard let o = oturum else { return }
        o.delegate = self
        o.activate()
    }

    // MARK: - Röle

    private func roleyiAc() {
        guard baglanti == nil else {
            // Röle ZATEN açık. Saat yeniden bağlanmak istiyorsa ona mevcut
            // durumu tekrar bildirmemiz gerekiyor: `durum` yalnızca
            // değiştiğinde haber veriyor, yani saat hiç `hazir` almadan
            // sonsuza kadar "Bağlanıyor…"da kalıyordu.
            baglanti?.durumuYinele()
            return
        }
        let b = NovaBaglanti(tasiyici: SoketTasiyici())

        b.yaziGeldi = { [weak self] m in
            self?.cerceveYolla("yazi", ["metin": m])
        }
        b.yanitGeldi = { [weak self] m, kismi in
            self?.cerceveYolla("yanit", ["metin": m, "kismi": kismi])
        }
        b.sesParcasiGeldi = { [weak self] veri, bicim, ara in
            self?.sesYolla(veri, bicim: bicim, ara: ara)
        }
        b.turBitti = { [weak self] in
            self?.cerceveYolla("bitti", [:])
        }
        b.durumDegisti = { [weak self] d in
            // Saat bağlantı durumunu da görmeli: parola yanlışsa ya da
            // bilgisayara ulaşılamıyorsa eskiden hiç haber gitmiyordu.
            switch d {
            case .hazir(let ses):
                self?.cerceveYolla("hazir", ["ses": ses])
            case .yetkisiz:
                self?.cerceveYolla("yetkisiz", [:])
            case .hata(let m):
                self?.cerceveYolla("hata", ["mesaj": m])
            case .kapali, .baglaniyor:
                break
            }
        }

        baglanti = b
        b.ac()
        DispatchQueue.main.async { self.roleAcik = true }
    }

    private func roleyiKapat() {
        baglanti?.kapat()
        baglanti = nil
        DispatchQueue.main.async { self.roleAcik = false }
    }

    // MARK: - Saate gönderme

    private func cerceveYolla(_ tur: String, _ alanlar: [String: Any]) {
        var d = alanlar
        d["tur"] = tur
        guard let veri = try? JSONSerialization.data(withJSONObject: d) else {
            return
        }
        saateYolla(["c": veri])
    }

    private func sesYolla(_ ham: Data, bicim: String, ara: Bool) {
        kuyruk.async { [weak self] in
            self?.sesYollaIc(ham, bicim: bicim, ara: ara)
        }
    }

    private func sesYollaIc(_ ham: Data, bicim: String, ara: Bool) {
        // Sıkıştırma başarısız olursa ham veriyi dilimleyerek yolluyoruz;
        // hız iyileştirmesi, çalışmanın ön koşulu değil.
        var veri = ham
        var tur = bicim
        if let kucuk = SesSikistirici.aac(ham, bicim: bicim) {
            veri = kucuk
            tur = "audio/mp4"
        }

        sonrakiKimlik &+= 1
        let kimlik = sonrakiKimlik
        let toplam = max(1, (veri.count + dilimBoyu - 1) / dilimBoyu)
        var k = 0
        var yer = veri.startIndex
        while yer < veri.endIndex {
            let son = veri.index(yer, offsetBy: dilimBoyu,
                                 limitedBy: veri.endIndex) ?? veri.endIndex
            saateYolla(["a": Data(veri[yer..<son]), "i": kimlik,
                        "k": k, "n": toplam, "b": tur, "d": ara])
            yer = son
            k += 1
        }
    }

    private func saateYolla(_ yuk: [String: Any]) {
        guard let o = oturum, o.isReachable else { return }
        o.sendMessage(yuk, replyHandler: nil, errorHandler: nil)
    }
}

extension SaatRolesi: WCSessionDelegate {

    func session(_ session: WCSession,
                 activationDidCompleteWith state: WCSessionActivationState,
                 error: Error?) {
        DispatchQueue.main.async { self.saatBagli = session.isReachable }
    }

    func sessionDidBecomeInactive(_ session: WCSession) {}

    func sessionDidDeactivate(_ session: WCSession) {
        session.activate()
    }

    func sessionReachabilityDidChange(_ session: WCSession) {
        DispatchQueue.main.async { self.saatBagli = session.isReachable }
        if !session.isReachable { roleyiKapat() }
    }

    func session(_ session: WCSession, didReceiveMessage m: [String: Any]) {
        kuyruk.async { [weak self] in
            guard let self else { return }
            if let komut = m["komut"] as? String {
                komut == "role_ac" ? self.roleyiAc() : self.roleyiKapat()
                return
            }
            // Saatten gelen çerçeveyi bilgisayara geçir. Röle bilerek APTAL:
            // içeriğe bakmıyor, ayrıştırmıyor, saklamıyor.
            if let d = m["c"] as? Data {
                self.roleyiAc()
                self.baglanti?.hamYolla(d)
            }
            if let d = m["m"] as? Data {
                self.baglanti?.sesGonder(d)
            }
        }
    }
}
