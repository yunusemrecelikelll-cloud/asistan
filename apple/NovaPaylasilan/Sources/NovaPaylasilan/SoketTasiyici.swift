import Foundation

/// Doğrudan WebSocket taşıyıcısı — telefon her zaman, saat ev ağındayken.
///
/// Kalıcı bağlantı tutuyoruz. Sesli bir tur HTTP'de dört ayrı istek demekti
/// (yazıya çevir, yanıt al, parçala, seslendir) ve her istek yeni bir el
/// sıkışma: yerel ağda ~30-60 ms, hücresel bağlantıda 150-300 ms. Kalıcı
/// kanalda el sıkışma bir kez oluyor; ses parçaları da hazır olur olmaz
/// sunucudan itiliyor, istemcinin sorması gerekmiyor.
public final class SoketTasiyici: NSObject, Tasiyici {

    public var metinGeldi: ((Data) -> Void)?
    public var ikiliGeldi: ((Data) -> Void)?
    public var durumDegisti: ((TasiyiciDurumu) -> Void)?

    public private(set) var ad = "doğrudan"

    /// Deneme sırasına göre adresler. Önce yerel ağ, sonra Tailscale:
    /// aynı ağdayken Tailscale üzerinden gitmek tur başına 20-60 ms ekliyor.
    private var adresler: [URL] = []
    private var sira = 0
    private var soket: URLSessionWebSocketTask?
    private var oturum: URLSession!
    private var denemeSayisi = 0
    private var kapatildi = false
    private let kuyruk = DispatchQueue(label: "nova.soket")

    /// Kaçıncı açılış denemesindeyiz. Süresi dolan denemenin, arada
    /// başlamış yeni bir denemeyi iptal etmesini engelliyor.
    private var acilisNo = 0
    /// Bu denemede sunucudan tek bir çerçeve bile geldi mi?
    private var cerceveGeldi = false

    /// Bir adrese bu kadar süre içinde yanıt gelmezse sıradakine geçilir.
    ///
    /// Eskiden yanlış adresteyken (evden çıkınca yerel ağ adresi, eve
    /// girince Tailscale) hata ancak soket zaman aşımına uğrayınca
    /// anlaşılıyordu — yani 30 saniye. Uygulama her açılışta o kadar
    /// "Bağlanıyor…" yazıyordu. Sunucu bağlantıyı kabul eder etmez `hazir`
    /// yolluyor; hücresel Tailscale'de bile 1,5 saniye fazlasıyla yeterli.
    private let adresSuresi: TimeInterval = 1.5

    /// Kapanınca kendiliğinden yeniden bağlansın mı. Saat, yol seçimini
    /// kendisi yönettiği için bunu kapatıyor.
    public var kendiliginden = true

    public override init() {
        super.init()
        let y = URLSessionConfiguration.default
        y.timeoutIntervalForRequest = 8
        y.waitsForConnectivity = false
        oturum = URLSession(configuration: y, delegate: nil, delegateQueue: nil)
    }

    public func ac() {
        kuyruk.async {
            self.kapatildi = false
            self.acIc()
        }
    }

    private func acIc() {
        soket?.cancel(with: .goingAway, reason: nil)
        adresler = [Ayarlar.ortak.yerelWsAdresi, Ayarlar.ortak.wsAdresi]
            .compactMap { $0 }
        guard !adresler.isEmpty else {
            bildir(.hata("Sunucu adresi girilmemiş."))
            return
        }
        if sira >= adresler.count { sira = 0 }
        ad = sira == 0 && adresler.count > 1 ? "yerel ağ" : "doğrudan"

        bildir(.acilliyor)
        let g = oturum.webSocketTask(with: adresler[sira])
        soket = g
        g.resume()
        acilisNo &+= 1
        cerceveGeldi = false
        let benimNom = acilisNo
        dinle(benimNom)
        bildir(.acik)

        // Adres tutmadıysa 30 saniye beklemeden sıradakine geç.
        guard adresler.count > 1 else { return }
        kuyruk.asyncAfter(deadline: .now() + adresSuresi) { [weak self] in
            guard let self, !self.kapatildi, self.kendiliginden,
                  self.acilisNo == benimNom, !self.cerceveGeldi else { return }
            self.sira = (self.sira + 1) % self.adresler.count
            self.acIc()
        }
    }

    public func kapat() {
        kuyruk.async {
            self.kapatildi = true
            self.soket?.cancel(with: .goingAway, reason: nil)
            self.soket = nil
            self.bildir(.kapali)
        }
    }

    // Gönderimler de `kuyruk` üzerinden gidiyor. `soket` alanını açma,
    // kapama ve yeniden bağlanma zaten orada değiştiriyor; buradan başka
    // bir iş parçacığından okumak veri yarışıydı. Mikrofon tamponları ses
    // yakalama iş parçacığından geldiği için bu gerçekten oluyordu.
    public func yolla(_ veri: Data) {
        let s = String(data: veri, encoding: .utf8) ?? "{}"
        kuyruk.async { [weak self] in
            self?.soket?.send(.string(s)) { [weak self] hata in
                if let hata { self?.koptu(hata) }
            }
        }
    }

    public func ikiliYolla(_ veri: Data) {
        kuyruk.async { [weak self] in
            self?.soket?.send(.data(veri)) { [weak self] hata in
                if let hata { self?.koptu(hata) }
            }
        }
    }

    /// ``no`` bu dinlemenin ait olduğu açılış denemesi.
    ///
    /// Süre dolup sıradaki adrese geçtiğimizde eski soket iptal ediliyor ve
    /// bu da bir "hata" bildirimi üretiyor. Kuşak numarası olmadan o
    /// bildirim yeni denemeyi de kopmuş sayıp ikinci bir yeniden bağlanma
    /// başlatıyordu — iki bağlantı birbiriyle yarışıyordu.
    private func dinle(_ no: Int) {
        soket?.receive { [weak self] sonuc in
            guard let self else { return }
            switch sonuc {
            case .failure(let hata):
                self.koptu(hata, no: no)
            case .success(let mesaj):
                self.kuyruk.async { self.cerceveGeldi = true }
                switch mesaj {
                case .string(let s): self.metinGeldi?(Data(s.utf8))
                case .data(let d): self.ikiliGeldi?(d)
                @unknown default: break
                }
                self.dinle(no)
            }
        }
    }

    private func koptu(_ hata: Error, no: Int? = nil) {
        kuyruk.async {
            guard !self.kapatildi else { return }
            if let no, no != self.acilisNo { return }   // eski deneme
            self.soket = nil
            self.bildir(.hata(hata.localizedDescription))
            guard self.kendiliginden else { return }

            // Sıradaki adresi dene: yerel ağ düştüyse Tailscale'e geç.
            self.sira = (self.sira + 1) % max(self.adresler.count, 1)
            self.denemeSayisi += 1
            // Artan bekleme ama 8 saniyede sabit: kullanıcı konuşmak
            // istediğinde hazır olmalıyız, sonsuza kadar geri çekilemeyiz.
            let bekle = min(pow(1.6, Double(self.denemeSayisi)), 8.0)
            self.kuyruk.asyncAfter(deadline: .now() + bekle) {
                if !self.kapatildi { self.acIc() }
            }
        }
    }

    private func bildir(_ d: TasiyiciDurumu) {
        if case .acik = d { denemeSayisi = 0 }
        DispatchQueue.main.async { self.durumDegisti?(d) }
    }
}
