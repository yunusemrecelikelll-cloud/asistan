import Foundation
import WatchKit

/// Konuşurken saatin ekranı sönmesin.
///
/// watchOS bileği indirince ekranı karartıyor, ama asıl sorun bu değil:
/// bilek kalkıkken bile uygulama birkaç saniye sonra arka plana düşüyor ve
/// konuşmanın ortasında ekran kapanıyor. Uzatılmış çalışma oturumu
/// (`WKExtendedRuntimeSession`) uygulamayı önde ve ekranı açık tutuyor.
///
/// Neden `mindfulness` türü: watchOS bu oturumları belirli kullanımlara
/// bağlıyor ve seçenekler arasında karşılıklı konuşmaya en yakın olan bu —
/// kullanıcının ekrana bakarak sürdürdüğü, dakikalarca süren bir etkinlik.
/// `workout` konum ve nabız izni istiyor, `smartAlarm` tek seferlik.
///
/// Oturum yalnızca mikrofon açıkken kuruluyor ve kayıt biter bitmez
/// kapanıyor: gereğinden uzun tutmak saatin pilini yer.
///
/// Kurulamazsa hiçbir şey bozulmuyor — ekran eskisi gibi sönüyor, konuşma
/// yine çalışıyor. Bu bir iyileştirme, çalışmanın ön koşulu değil.
final class EkranAcik: NSObject {

    static let ortak = EkranAcik()

    private var oturum: WKExtendedRuntimeSession?

    /// Konuşma başladı — ekranı açık tut.
    func basla() {
        guard oturum == nil else { return }
        let o = WKExtendedRuntimeSession()
        o.delegate = self
        oturum = o
        o.start()
    }

    /// Konuşma bitti — bırak, pil yanmasın.
    func bitir() {
        oturum?.invalidate()
        oturum = nil
    }
}

extension EkranAcik: WKExtendedRuntimeSessionDelegate {

    func extendedRuntimeSessionDidStart(_ s: WKExtendedRuntimeSession) {}

    /// Sistem "birazdan bitireceğim" diyor. Yapacak bir şey yok; kullanıcı
    /// konuşmaya devam ediyorsa bir sonraki turda yenisi kurulacak.
    func extendedRuntimeSessionWillExpire(_ s: WKExtendedRuntimeSession) {}

    func extendedRuntimeSession(
        _ s: WKExtendedRuntimeSession,
        didInvalidateWith reason: WKExtendedRuntimeSessionInvalidationReason,
        error: Error?
    ) {
        // Kendi kapattıysak da sistem kapattıysa da referansı bırakıyoruz;
        // yoksa `basla()` bir daha hiç yeni oturum kurmaz.
        if oturum === s { oturum = nil }
    }
}
