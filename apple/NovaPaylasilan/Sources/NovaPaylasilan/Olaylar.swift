import Foundation

/// Sunucudan gelen değişiklik bildirimleri — masaüstüyle canlı senkron.
///
/// Sunucu her değişikliği yayınlıyor (görev eklendi, tamamlandı, proje
/// güncellendi…) ve bu bildirimler zaten açık olan sesli kanaldan telefona
/// düşüyordu — ama kimse dinlemiyordu. Ekranlar yalnızca açılışta ve elle
/// çekince tazeleniyordu, yani masaüstünde bir görevi tamamlayınca telefon
/// eski hâli göstermeye devam ediyordu.
///
/// Burada tek bir sayaç var: bir olay geldiğinde artıyor, açık olan
/// ekranlar da onu izleyip kendini yeniliyor. Hangi ekranın hangi olayla
/// ilgilendiğini burada bilmiyoruz — ekran kendi karar veriyor.
@MainActor
public final class Olaylar: ObservableObject {

    public static let ortak = Olaylar()

    /// Her olayda artıyor. Ekranlar bunu izliyor.
    @Published public private(set) var sayac = 0
    /// Son olayın türü: "gorev", "proje", "yasam", "bildirim"…
    @Published public private(set) var sonTur = ""

    private init() {}

    public func bildir(_ tur: String) {
        sonTur = tur
        sayac &+= 1
    }

    /// Bu ekran bu olayla ilgileniyor mu?
    ///
    /// Yaşam kaydı değiştiğinde atölye ekranını tazelemenin anlamı yok;
    /// gereksiz istek hem pil hem ağ.
    public func ilgilendirir(_ turler: [String]) -> Bool {
        sonTur.isEmpty || turler.contains(sonTur)
    }
}
