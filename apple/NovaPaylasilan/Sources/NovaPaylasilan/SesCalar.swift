import AVFoundation
import Foundation

/// Sunucudan gelen ses parçalarını KESİNTİSİZ çalar.
///
/// Sunucu cümle cümle gönderiyor: ilk cümle hazır olur olmaz yola çıkıyor,
/// kalanı biz çalarken üretiliyor. Her parça için ayrı bir AVAudioPlayer
/// kursaydık parçalar arasında 100-200 ms boşluk olurdu ve konuşma kesik
/// kesik duyulurdu. Tek bir AVAudioPlayerNode'a arka arkaya tampon
/// sıraya koyunca boşluk kalmıyor.
public final class SesCalar {

    /// Anlık çıkış şiddeti 0…1 — küre konuşurken buna göre dağılıyor.
    public var seviyeDegisti: ((Float) -> Void)?
    /// Sıradaki her şey çalındığında.
    public var bitti: (() -> Void)?

    public private(set) var caliyor = false

    private let motor = AVAudioEngine()
    private let dugum = AVAudioPlayerNode()
    private var kuruldu = false
    private var mevcutBicim: AVAudioFormat?
    private var bekleyen = 0
    /// Kesme kuşağı. `kes()` bunu artırıyor; eski kuşağa ait tamponların
    /// tamamlanma bildirimleri sayacı bozmasın diye.
    ///
    /// Eskiden `kes()` önce `dugum.stop()` çağırıp sonra `bekleyen = 0`
    /// yapıyordu. Oysa `stop()` sıradaki tamponların tamamlanma
    /// bildirimlerini TETİKLİYOR; her biri sıfırlanmış sayacı bir daha
    /// azaltıyordu. Sayaç eksiye düşünce `kalan == 0` bir daha hiç tutmuyor,
    /// `bitti` bir daha hiç çağrılmıyordu — yani kullanıcı Nova'nın sözünü
    /// bir kez kestiğinde sürekli dinleme kipi kalıcı olarak ölüyordu.
    private var kusak = 0
    private let kilit = NSLock()

    public init() {
        gozle()
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    // MARK: - Kurulum

    /// Ses grafiğini kur. Biçim değiştiyse ya da motor bir kesinti sonrası
    /// durduysa yeniden kurulur.
    private func kur(_ bicim: AVAudioFormat) throws {
        if kuruldu, motor.isRunning, let m = mevcutBicim,
           m.sampleRate == bicim.sampleRate,
           m.channelCount == bicim.channelCount {
            return
        }
        if kuruldu { sok() }

        motor.attach(dugum)
        motor.connect(dugum, to: motor.mainMixerNode, format: bicim)

        // Çıkışı dinleyip şiddeti dışarı veriyoruz; küre bunu kullanıyor.
        motor.mainMixerNode.installTap(onBus: 0, bufferSize: 1024,
                                       format: nil) { [weak self] t, _ in
            // Motor ön ısıtma yüzünden boşta da dönüyor; sessizliği
            // saniyede 40 kez ana kuyruğa taşımanın anlamı yok.
            guard let self, self.caliyor,
                  let veri = t.floatChannelData else { return }
            let n = Int(t.frameLength)
            var toplam: Float = 0
            for i in 0..<n { toplam += veri[0][i] * veri[0][i] }
            let s = n > 0 ? sqrt(toplam / Float(n)) : 0
            DispatchQueue.main.async { self.seviyeDegisti?(min(s * 4, 1)) }
        }

        motor.prepare()
        try motor.start()
        kuruldu = true
        mevcutBicim = bicim
    }

    /// Grafiği söktür. Biçim değişiminde ve kesinti sonrası yeniden kurmadan
    /// önce çağrılıyor; yarım kurulmuş bir motora bağlanmak cızırtı üretiyor.
    private func sok() {
        dugum.stop()
        motor.mainMixerNode.removeTap(onBus: 0)
        motor.stop()
        motor.disconnectNodeOutput(dugum)
        motor.detach(dugum)
        kuruldu = false
        mevcutBicim = nil
    }

    /// Ses motorunu ilk parça GELMEDEN kur.
    ///
    /// `AVAudioEngine.start()` 50-150 ms sürüyor ve eskiden bu bedel ilk ses
    /// parçası elimize geçtiğinde ödeniyordu — yani tam kritik yolun
    /// üstünde. Tur başlarken (kullanıcı sustuğu an) çağırınca ses geldiğinde
    /// motor çoktan dönüyor oluyor.
    ///
    /// Sesli turda oturum kayıttan dolayı zaten etkin; ek bir maliyeti yok.
    public func hazirla() {
        guard !kuruldu || !motor.isRunning else { return }
        // Sunucu 24 kHz mono üretiyor (XTTS de, AAC'ye çevrilmiş hâli de).
        // Tutmazsa `kur()` ilk parçada yeniden kurar — kaybımız yok.
        guard let tahmin = AVAudioFormat(commonFormat: .pcmFormatFloat32,
                                         sampleRate: 24_000, channels: 1,
                                         interleaved: false) else { return }
        try? SesOturumu.ac()
        try? kur(tahmin)
    }

    // MARK: - Kesintiler

    /// Telefon araması, Siri ya da ses sunucusunun çökmesi motoru durduruyor.
    ///
    /// Bunu dinlemezsek `kuruldu` true kalıyor, `kur()` erken dönüyor ve ses
    /// KALICI olarak susuyordu — üstelik hiçbir hata görünmeden. Kayıt ve
    /// çalma ayrı motorlar ama aynı oturumu paylaştığı için ikisi de etkileniyor.
    private func gozle() {
        let m = NotificationCenter.default
        m.addObserver(self, selector: #selector(kesinti(_:)),
                      name: AVAudioSession.interruptionNotification,
                      object: nil)
        m.addObserver(self, selector: #selector(sifirlandi(_:)),
                      name: AVAudioSession.mediaServicesWereResetNotification,
                      object: nil)
    }

    @objc private func kesinti(_ b: Notification) {
        guard let ham = b.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
              let tur = AVAudioSession.InterruptionType(rawValue: ham)
        else { return }
        if tur == .began { kes() }
    }

    @objc private func sifirlandi(_ b: Notification) {
        // Ses sunucusu çöküp yeniden doğduğunda bütün nesneler geçersiz.
        kilit.lock(); kusak &+= 1; bekleyen = 0; kilit.unlock()
        caliyor = false
        kuruldu = false
        mevcutBicim = nil
    }

    // MARK: - Sıraya ekleme

    /// Ses parçasını sıraya ekle. Çalma zaten sürüyorsa arkasına eklenir.
    ///
    /// ``bicim`` sunucunun bildirdiği MIME türü. Ses klonu (XTTS) düştüğünde
    /// sunucu sessizce edge-tts'e geçip **mp3** yolluyor; eskiden yalnızca WAV
    /// çözülüyordu ve o durumda telefonda hiç ses çıkmıyordu.
    @discardableResult
    public func sirayaEkle(_ veri: Data, bicim: String = "audio/wav") -> Bool {
        guard let (sesBicimi, tampon) = Self.coz(veri, bicim: bicim) else {
            return false
        }
        do {
            try SesOturumu.ac()
            try kur(sesBicimi)
        } catch {
            return false
        }

        kilit.lock()
        bekleyen += 1
        let benimKusagim = kusak
        kilit.unlock()
        caliyor = true

        dugum.scheduleBuffer(tampon) { [weak self] in
            guard let self else { return }
            self.kilit.lock()
            // Kesildikten sonra gelen eski bildirimler sayacı bozmasın.
            guard benimKusagim == self.kusak else {
                self.kilit.unlock()
                return
            }
            self.bekleyen -= 1
            let kalan = self.bekleyen
            self.kilit.unlock()
            if kalan == 0 {
                self.caliyor = false
                DispatchQueue.main.async {
                    self.seviyeDegisti?(0)
                    self.bitti?()
                }
            }
        }
        if !dugum.isPlaying { dugum.play() }
        return true
    }

    /// Kullanıcı sözü kesince: çalmayı hemen bırak.
    ///
    /// Karşılıklı konuşmanın olmazsa olmazı. Nova konuşurken kullanıcı
    /// araya girdiğinde cümlenin bitmesini beklemek sohbeti öldürüyor.
    ///
    /// `bitti` BURADA çağrılmıyor: kesmeyi isteyen taraf (`sustur()`,
    /// `dinlemeyeBasla()`) durumu zaten kendisi belirliyor. Buradan da
    /// bildirseydik sürekli dinleme kipinde kendi kendini tetikleyen bir
    /// döngüye kapı açılıyordu.
    public func kes() {
        kilit.lock()
        kusak &+= 1
        bekleyen = 0
        kilit.unlock()
        caliyor = false
        dugum.stop()
        DispatchQueue.main.async { self.seviyeDegisti?(0) }
    }

    // MARK: - Çözme

    /// Sunucunun bildirdiği biçime göre uygun çözücüyü seç.
    public static func coz(_ veri: Data, bicim: String)
    -> (AVAudioFormat, AVAudioPCMBuffer)? {
        // Biçim başlığına değil, verinin kendisine de bakıyoruz: sunucu
        // yanlış MIME bildirse bile doğru çözücüye gitsin.
        if veri.prefix(4) == Data("RIFF".utf8) { return wavCoz(veri) }
        if bicim.contains("wav") { return wavCoz(veri) }
        return dosyadanCoz(veri, uzanti: uzanti(bicim))
    }

    private static func uzanti(_ bicim: String) -> String {
        if bicim.contains("mpeg") || bicim.contains("mp3") { return "mp3" }
        if bicim.contains("mp4") || bicim.contains("aac") { return "m4a" }
        if bicim.contains("opus") || bicim.contains("ogg") { return "ogg" }
        return "mp3"
    }

    /// WAV dışındaki biçimler (edge-tts mp3) için platform çözücüsü.
    ///
    /// AVAudioFile dosya yolu istiyor; geçici dosyaya yazmak parça başına
    /// birkaç milisaniye. Kendi mp3 çözücümüzü yazmanın alternatifi bu.
    static func dosyadanCoz(_ veri: Data, uzanti: String)
    -> (AVAudioFormat, AVAudioPCMBuffer)? {
        let yol = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension(uzanti)
        defer { try? FileManager.default.removeItem(at: yol) }
        do {
            try veri.write(to: yol)
            let dosya = try AVAudioFile(forReading: yol)
            let bicim = dosya.processingFormat
            guard dosya.length > 0,
                  let tampon = AVAudioPCMBuffer(
                    pcmFormat: bicim,
                    frameCapacity: AVAudioFrameCount(dosya.length))
            else { return nil }
            try dosya.read(into: tampon)
            guard tampon.frameLength > 0 else { return nil }
            return (bicim, tampon)
        } catch {
            return nil
        }
    }

    /// Basit WAV çözücü. AVAudioFile dosya yolu istiyor; veriyi diske yazıp
    /// geri okumak parça başına ~10 ms ve gereksiz disk trafiği demekti.
    static func wavCoz(_ veri: Data) -> (AVAudioFormat, AVAudioPCMBuffer)? {
        guard veri.count > 44,
              veri.prefix(4) == Data("RIFF".utf8) else { return nil }

        func u32(_ k: Int) -> Int {
            Int(veri[k]) | Int(veri[k + 1]) << 8
                | Int(veri[k + 2]) << 16 | Int(veri[k + 3]) << 24
        }
        func u16(_ k: Int) -> Int { Int(veri[k]) | Int(veri[k + 1]) << 8 }

        var k = 12
        var kanal = 1, oran = 24_000, bit = 16
        var sesBaslangic = -1, sesUzunluk = 0

        // Öbekleri gerçekten dolaşıyoruz: XTTS'in ürettiği WAV'larda fmt ve
        // data arasında başka öbekler olabiliyor, sabit 44 bayt varsaymak
        // ara ara cızırtıya yol açıyordu.
        while k + 8 <= veri.count {
            let ad = String(bytes: veri[k..<k + 4], encoding: .ascii) ?? ""
            let boy = u32(k + 4)
            let govde = k + 8
            if ad == "fmt " && govde + 16 <= veri.count {
                kanal = max(1, u16(govde + 2))
                oran = u32(govde + 4)
                bit = u16(govde + 14)
            } else if ad == "data" {
                sesBaslangic = govde
                sesUzunluk = min(boy, veri.count - govde)
                break
            }
            k = govde + boy + (boy % 2)          // öbekler çift hizalı
        }
        guard sesBaslangic > 0, sesUzunluk > 0, bit == 16,
              oran > 0, kanal > 0 else { return nil }

        guard let bicim = AVAudioFormat(
            commonFormat: .pcmFormatFloat32, sampleRate: Double(oran),
            channels: AVAudioChannelCount(kanal), interleaved: false),
            let tampon = AVAudioPCMBuffer(
                pcmFormat: bicim,
                frameCapacity: AVAudioFrameCount(sesUzunluk / (2 * kanal)))
        else { return nil }

        let cerceve = sesUzunluk / (2 * kanal)
        guard cerceve > 0 else { return nil }
        tampon.frameLength = AVAudioFrameCount(cerceve)
        guard let hedef = tampon.floatChannelData else { return nil }

        veri.withUnsafeBytes { (ham: UnsafeRawBufferPointer) in
            let kaynak = ham.baseAddress!.advanced(by: sesBaslangic)
            for c in 0..<cerceve {
                for kan in 0..<kanal {
                    let ornek = kaynak.loadUnaligned(
                        fromByteOffset: (c * kanal + kan) * 2, as: Int16.self)
                    hedef[kan][c] = Float(Int16(littleEndian: ornek)) / 32768.0
                }
            }
        }
        return (bicim, tampon)
    }
}
