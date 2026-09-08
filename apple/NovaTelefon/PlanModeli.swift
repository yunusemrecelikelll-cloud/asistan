import NovaPaylasilan
import SwiftUI

/// Plan ekranının durumu. Sunucu tek gerçeklik kaynağı.
///
/// Yerelde hiçbir şey saklamıyoruz: her eylemden sonra listeyi sunucudan
/// yeniden okuyoruz. Masaüstü, telefon ve otomatik mentör aynı veriyi
/// değiştirdiği için "iyimser güncelleme" burada yanlış olurdu — ekranda
/// tamamlanmış görünen bir işin sunucuda ertelenmiş olması en can sıkıcı
/// hata türü.
@MainActor
final class PlanModeli: ObservableObject {

    @Published private(set) var bugun: Gun?
    @Published private(set) var hafta: Hafta?
    @Published private(set) var yukleniyor = false
    @Published var hata: String?

    func yenile() async {
        yukleniyor = true
        defer { yukleniyor = false }
        do {
            async let g = Api.ortak.bugun()
            async let h = Api.ortak.hafta()
            let (gun, haf) = try await (g, h)
            bugun = gun
            hafta = haf
            hata = nil
            // Bildirimleri her tazelemede yeniden kuruyoruz: ertelenen ya
            // da tamamlanan bir işin bildirimi çalmaya devam ederse
            // uygulama güvenilmez oluyor.
            await Bildirimler.ortak.planla(gun.gorevler)
        } catch {
            hata = (error as? Api.Hata)?.errorDescription
                ?? error.localizedDescription
        }
    }

    // MARK: - Eylemler

    func basla(_ g: Gorev) async { await calistir { try await Api.ortak.gorevBasla(g.id) } }
    func tamamla(_ g: Gorev) async { await calistir { try await Api.ortak.gorevTamamla(g.id) } }
    func ertele(_ g: Gorev) async { await calistir { try await Api.ortak.gorevErtele(g.id) } }
    func sil(_ g: Gorev) async { await calistir { try await Api.ortak.gorevSil(g.id) } }

    private func calistir(_ is_: @escaping () async throws -> Data) async {
        do {
            _ = try await is_()
            await yenile()
        } catch {
            hata = (error as? Api.Hata)?.errorDescription
                ?? error.localizedDescription
        }
    }
}
