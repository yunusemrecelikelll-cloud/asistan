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
        //
        // .allowBluetooth (HFP — kulaklığın MİKROFONUNU da kullanmak)
        // watchOS'ta ancak 11.0'da geldi. Hedefimiz watchOS 10, o yüzden
        // koşullu ekliyoruz: 10'da kulaklıktan çalıyor ama mikrofon saatin
        // kendisi oluyor, 11'de ikisi de kulaklıktan.
        var secenekler: AVAudioSession.CategoryOptions = [.duckOthers]
        if #available(watchOS 11.0, *) {
            secenekler.insert(.allowBluetooth)
        }
        try o.setCategory(.playAndRecord, mode: .voiceChat,
                          options: secenekler)
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
