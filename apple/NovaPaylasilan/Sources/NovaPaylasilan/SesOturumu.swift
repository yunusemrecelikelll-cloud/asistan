import AVFoundation

/// Ses oturumunu tek yerden kuruyoruz.
///
/// Kayıt ve çalma AYNI oturumu paylaşmak zorunda: ikisi ayrı ayrı
/// yapılandırırsa sonuncusu öncekini eziyor ve karşılıklı konuşma bozuluyor
/// (mikrofon kapanıyor ya da hoparlör kulaklığa düşüyor).
///
/// `.voiceChat` modu kritik: donanım yankı bastırmayı açıyor, böylece Nova
/// konuşurken mikrofon açık kalabiliyor ve Nova kendi sesini duyup kendini
/// tetiklemiyor. Bu olmadan "sürekli dinleme" kullanılamaz.
public enum SesOturumu {

    public static func ac() throws {
        let o = AVAudioSession.sharedInstance()

        #if os(watchOS)
        // watchOS'ta .defaultToSpeaker yok; saat çıkışı zaten hoparlör ya da
        // eşleşmiş kulaklık.
        try o.setCategory(.playAndRecord, mode: .voiceChat,
                          options: [.duckOthers, .allowBluetooth])
        #else
        try o.setCategory(.playAndRecord, mode: .voiceChat,
                          options: [.duckOthers, .allowBluetooth,
                                    .defaultToSpeaker])
        #endif

        try o.setActive(true, options: .notifyOthersOnDeactivation)
    }

    public static func kapat() {
        try? AVAudioSession.sharedInstance()
            .setActive(false, options: .notifyOthersOnDeactivation)
    }
}
