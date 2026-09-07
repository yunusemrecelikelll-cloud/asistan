// swift-tools-version: 5.9
import PackageDescription

// iPhone ve Apple Watch hedeflerinin ORTAK çekirdeği. Protokol, bağlantı,
// ses yakalama ve çalma burada; her iki uygulama da bunu içe alıyor.
// Böylece saat ile telefon arasında davranış farkı oluşmuyor.
let package = Package(
    name: "NovaPaylasilan",
    platforms: [.iOS(.v17), .watchOS(.v10)],
    products: [
        .library(name: "NovaPaylasilan", targets: ["NovaPaylasilan"])
    ],
    targets: [
        .target(name: "NovaPaylasilan"),
        .testTarget(name: "NovaPaylasilanTestleri",
                    dependencies: ["NovaPaylasilan"])
    ]
)
