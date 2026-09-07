import AVFoundation
import Foundation

/// Mikrofon yakalama — konuşurken parça parça gönderir.
///
/// Neden AVAudioEngine, neden AVAudioRecorder değil:
///
/// AVAudioRecorder kaydı dosyaya yazar ve dosyayı ancak durdurunca
/// kapatır. Yani kullanıcı sustuktan SONRA yükleme başlıyor; 10 saniyelik
/// konuşmada bu tur başına bir saniye daha bekleme demek. AVAudioEngine
/// tamponları anında verdiği için konuşma sürerken göndermeye başlıyoruz;
/// kullanıcı sustuğunda ses zaten sunucuda oluyor.
///
/// 16 kHz mono gönderiyoruz — Whisper zaten bu oranda çalışıyor, cihazda
/// indirgemek hem veriyi dörtte birine düşürüyor hem sunucuda bir dönüştürme
/// adımını kaldırıyor.
public final class SesKayit {

    public enum Hata: Error {
        case izinYok
        case motorBaslamadi(String)
    }

    /// Ham PCM parçası hazır olduğunda çağrılır (gönderim için).
    public var parcaHazir: ((Data) -> Void)?
    /// Anlık ses şiddeti 0…1 — küreyi canlandırmak için.
    public var seviyeDegisti: ((Float) -> Void)?
    /// Konuşma bitti sayılacak kadar sessizlik olduğunda.
    public var sessizlikAlgilandi: (() -> Void)?

    public private(set) var kaydediyor = false

    private let motor = AVAudioEngine()
    private var donusturucu: AVAudioConverter?
    private let hedefBicim = AVAudioFormat(
        commonFormat: .pcmFormatInt16, sampleRate: 16_000,
        channels: 1, interleaved: true)!

    private var toplananBayt = 0
    private var sonSesZamani = Date()
    private var sessizlikZamanlayici: Timer?

    /// Bu eşiğin altı sessizlik sayılır. Deneyerek bulundu: telefon
    /// hoparlöründen gelen yankı bu değerin altında kalıyor.
    public var sessizlikEsigi: Float = 0.012
    /// Kaç saniye sessizlikten sonra tur bitmiş sayılsın.
    ///
    /// Bu süre her turun sonuna DOĞRUDAN ekleniyor: kullanıcı sustuktan
    /// sonra bu kadar bekleyip öyle yolluyoruz. 0,7'den 0,55'e çekmek tur
    /// başına 150 ms kazandırıyor. Daha aşağısı cümle içi soluklanmayı
    /// "bitti" sanmaya başlıyor.
    public var sessizlikSuresi: TimeInterval = 0.55

    /// Kayıt bir kesintiyle (telefon araması, Siri) yarıda kaldı.
    public var kesintiyeUgradi: (() -> Void)?

    public init() {
        // Kesintiyi dinlemezsek motor durduğu hâlde `kaydediyor` true kalıyor:
        // arayüz "Dinliyorum" gösteriyor, mikrofon ölü, tur hiç kapanmıyordu.
        NotificationCenter.default.addObserver(
            self, selector: #selector(kesinti(_:)),
            name: AVAudioSession.interruptionNotification, object: nil)
        NotificationCenter.default.addObserver(
            self, selector: #selector(sifirlandi(_:)),
            name: AVAudioSession.mediaServicesWereResetNotification,
            object: nil)
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    @objc private func kesinti(_ b: Notification) {
        guard let ham = b.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
              let tur = AVAudioSession.InterruptionType(rawValue: ham),
              tur == .began, kaydediyor else { return }
        bitir()
        DispatchQueue.main.async { self.kesintiyeUgradi?() }
    }

    @objc private func sifirlandi(_ b: Notification) {
        guard kaydediyor else { return }
        bitir()
        DispatchQueue.main.async { self.kesintiyeUgradi?() }
    }

    /// İzin zaten verilmiş mi? Eşzamanlı okunuyor.
    public var izinVar: Bool {
        AVAudioApplication.shared.recordPermission == .granted
    }

    /// Mikrofon izni.
    ///
    /// İzin daha önce verilmişse HEMEN dönüyoruz. Eskiden her turda
    /// `requestRecordPermission` çağrılıyordu; izin verilmiş olsa bile bu
    /// eşzamansız bir gidiş dönüş demek ve kaydın başlamasını geciktiriyordu.
    /// Konuşmaya başlama anı doğrudan buna bağlı.
    public func izinIste(_ tamamlandi: @escaping (Bool) -> Void) {
        if izinVar {
            tamamlandi(true)
            return
        }
        AVAudioApplication.requestRecordPermission { izin in
            DispatchQueue.main.async { tamamlandi(izin) }
        }
    }

    public func basla() throws {
        guard !kaydediyor else { return }

        // .voiceChat modu donanım yankı bastırmayı açıyor: Nova konuşurken
        // mikrofon açık kalabiliyor, kendi sesini duyup kendini tetiklemiyor.
        // Bu, karşılıklı konuşmanın çalışmasının tek sebebi.
        try SesOturumu.ac()

        let giris = motor.inputNode
        let kaynakBicim = giris.outputFormat(forBus: 0)
        guard kaynakBicim.sampleRate > 0 else {
            throw Hata.motorBaslamadi("giriş biçimi okunamadı")
        }
        donusturucu = AVAudioConverter(from: kaynakBicim, to: hedefBicim)

        toplananBayt = 0
        sonSesZamani = Date()

        giris.removeTap(onBus: 0)
        giris.installTap(onBus: 0, bufferSize: 2048, format: kaynakBicim) {
            [weak self] tampon, _ in
            self?.tamponGeldi(tampon)
        }

        motor.prepare()
        do {
            try motor.start()
        } catch {
            // Yarım kurulmuş tap bir sonraki denemede motoru bozuyor.
            giris.removeTap(onBus: 0)
            throw Hata.motorBaslamadi(error.localizedDescription)
        }
        kaydediyor = true
        sessizligiIzle()
    }

    @discardableResult
    public func bitir() -> Int {
        guard kaydediyor else { return 0 }
        kaydediyor = false
        sessizlikZamanlayici?.invalidate()
        sessizlikZamanlayici = nil
        motor.inputNode.removeTap(onBus: 0)
        motor.stop()
        return toplananBayt
    }

    // MARK: - İç işler

    private func tamponGeldi(_ tampon: AVAudioPCMBuffer) {
        guard let donusturucu, let veriler = tampon.floatChannelData else {
            return
        }

        // Şiddet: kare ortalamanın kökü. Küre animasyonu ve sessizlik
        // algılaması aynı ölçüyü kullanıyor.
        let n = Int(tampon.frameLength)
        var toplam: Float = 0
        for i in 0..<n { toplam += veriler[0][i] * veriler[0][i] }
        let siddet = n > 0 ? sqrt(toplam / Float(n)) : 0
        DispatchQueue.main.async { self.seviyeDegisti?(min(siddet * 6, 1)) }
        if siddet > sessizlikEsigi { sonSesZamani = Date() }

        // 16 kHz mono int16'ya indir
        let oran = hedefBicim.sampleRate / tampon.format.sampleRate
        let kapasite = AVAudioFrameCount(Double(tampon.frameLength) * oran) + 64
        guard let cikti = AVAudioPCMBuffer(pcmFormat: hedefBicim,
                                           frameCapacity: kapasite) else {
            return
        }
        var verildi = false
        var hata: NSError?
        donusturucu.convert(to: cikti, error: &hata) { _, durum in
            if verildi {
                durum.pointee = .noDataNow
                return nil
            }
            verildi = true
            durum.pointee = .haveData
            return tampon
        }
        guard hata == nil, cikti.frameLength > 0,
              let int16 = cikti.int16ChannelData else { return }

        let baytSayisi = Int(cikti.frameLength) * 2
        let veri = Data(bytes: int16[0], count: baytSayisi)
        toplananBayt += baytSayisi
        parcaHazir?(veri)
    }

    private func sessizligiIzle() {
        DispatchQueue.main.async {
            self.sessizlikZamanlayici?.invalidate()
            self.sessizlikZamanlayici = Timer.scheduledTimer(
                withTimeInterval: 0.05, repeats: true
            ) { [weak self] _ in
                guard let self, self.kaydediyor else { return }
                // En az yarım saniyelik ses toplanmadan sessizliğe bakmıyoruz;
                // aksi hâlde kayıt daha başlarken kendini kapatıyor.
                guard self.toplananBayt > 16_000 else { return }
                if Date().timeIntervalSince(self.sonSesZamani)
                    > self.sessizlikSuresi {
                    self.sessizlikAlgilandi?()
                }
            }
        }
    }

    /// Ham 16 kHz mono PCM'e WAV başlığı ekler.
    ///
    /// Sunucu kaydı dosya olarak açıyor; başlıksız ham PCM'i çözemiyor.
    /// Başlığı burada üretmek, gönderilen 44 baytı saymazsak bedava.
    public static func wavBasligi(veriUzunlugu: Int, oran: Int = 16_000,
                                  kanal: Int = 1, bit: Int = 16) -> Data {
        var b = Data()
        func yaz32(_ d: Int) { b.append(contentsOf: withUnsafeBytes(
            of: UInt32(d).littleEndian) { Array($0) }) }
        func yaz16(_ d: Int) { b.append(contentsOf: withUnsafeBytes(
            of: UInt16(d).littleEndian) { Array($0) }) }

        b.append(contentsOf: Array("RIFF".utf8))
        yaz32(36 + veriUzunlugu)
        b.append(contentsOf: Array("WAVEfmt ".utf8))
        yaz32(16)                                   // fmt öbek boyu
        yaz16(1)                                    // PCM
        yaz16(kanal)
        yaz32(oran)
        yaz32(oran * kanal * bit / 8)               // saniyedeki bayt
        yaz16(kanal * bit / 8)                      // blok hizası
        yaz16(bit)
        b.append(contentsOf: Array("data".utf8))
        yaz32(veriUzunlugu)
        return b
    }
}
