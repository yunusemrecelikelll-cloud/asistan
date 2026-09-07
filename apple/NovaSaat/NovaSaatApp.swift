import NovaPaylasilan
import SwiftUI

@main
struct NovaSaatApp: App {

    /// Saatin tek yolu telefon rölesi. Doğrudan Wi-Fi yolu bilerek yok:
    /// saatte sunucu adresi ve parola girecek bir ekran olmadığı için o yol
    /// zaten hiç kurulamıyordu, ama denenmesi her bağlanışa 1,2 saniye
    /// bindiriyordu. Saat "aptal uç": konuşur, dinler, gerisi telefonda.
    @StateObject private var oturum = Oturum(tasiyici: RoleTasiyici())
    @Environment(\.scenePhase) private var evre

    var body: some Scene {
        WindowGroup {
            SaatGorunumu()
                .environmentObject(oturum)
                .onAppear { oturum.basla() }
                .onChange(of: evre) { _, yeni in
                    // watchOS bileği düşünce bağlantıyı acımasızca kesiyor.
                    // Uygulama öne gelir gelmez yeniden bağlanıyoruz ki
                    // kullanıcı bileğini kaldırıp hemen konuşabilsin.
                    if yeni == .active { oturum.basla() }
                }
        }
    }
}
