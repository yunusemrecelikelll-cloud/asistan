import AVFoundation
import Foundation

/// Saate giden sesi küçültür.
///
/// Saat ile telefon arasındaki bağ Bluetooth. XTTS 24 kHz 16-bit WAV
/// üretiyor: saniyede 48 KB. İki saniyelik bir cümle 96 KB ve bu bağda
/// yarım saniyeden fazla aktarım demek — üstelik `WCSession.sendMessage`
/// tek mesajda ~64 KB'ı geçemediği için parçalamak da gerekiyor.
///
/// Aynı sesi AAC'ye çevirince 96 KB → ~8 KB oluyor. Kodlama telefonda
/// 10-20 ms sürüyor, kazanılan aktarım süresi ise yüzlerce milisaniye.
/// Saatte ilk sesin duyulma anı doğrudan bu farka bağlı.
///
/// Sıkıştırma başarısız olursa çağıran taraf ham veriyi parçalayarak
/// yollamaya devam ediyor; hız için yapılan bir iyileştirme, çalışmanın
/// ön koşulu değil.
public enum SesSikistirici {

    /// AAC (m4a) karşılığını üret. Beceremezse `nil`.
    public static func aac(_ veri: Data, bicim: String,
                           bitHizi: Int = 32_000) -> Data? {
        guard let (kaynak, tampon) = SesCalar.coz(veri, bicim: bicim),
              tampon.frameLength > 0 else { return nil }

        let yol = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("m4a")
        defer { try? FileManager.default.removeItem(at: yol) }

        let ayar: [String: Any] = [
            AVFormatIDKey: kAudioFormatMPEG4AAC,
            AVSampleRateKey: kaynak.sampleRate,
            AVNumberOfChannelsKey: Int(kaynak.channelCount),
            AVEncoderBitRateKey: bitHizi,
        ]

        do {
            // AVAudioFile veriyi ancak nesne serbest kalınca diske basıyor.
            // Dosyayı okumadan ÖNCE açıkça bırakmazsak yarım dosya okuyoruz.
            var yazici: AVAudioFile? = try AVAudioFile(forWriting: yol,
                                                       settings: ayar)
            try yazici?.write(from: tampon)
            yazici = nil

            let cikti = try Data(contentsOf: yol)
            // Sıkıştırma işe yaramadıysa (çok kısa parça, kodlayıcı ek yükü)
            // ham veriyi yollamak daha ucuz.
            return cikti.count < veri.count ? cikti : nil
        } catch {
            return nil
        }
    }
}
