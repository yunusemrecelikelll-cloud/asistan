"""Canlı olay akışı — masaüstü ve telefonun aynı anda güncel kalması için.

Uzun yoklama (long-poll) kullanıyoruz: istemci ``/api/olaylar?since=N`` çağırır,
yeni olay yoksa istek en fazla ``BEKLEME`` saniye bekletilir. Yeni bir olay
yayınlandığı anda bekleyen tüm istemciler uyandırılır.

WebSocket yerine bunu seçtim: olaylar arka plan iş parçacıklarından (dispatch,
auto, bulk) yayınlanıyor; uzun yoklamada asyncio ile iş parçacığı arasında
köprü kurmak gerekmiyor, hem tarayıcı hem Flutter tarafında aynı basit HTTP
çağrısıyla çalışıyor.
"""

from __future__ import annotations

import threading
import time
from collections import deque

BEKLEME = 25          # saniye; istemci bunu aşarsa boş dönüp yeniden sorar
GECMIS = 300          # bellekte tutulan olay sayısı

_kilit = threading.Condition()
_olaylar: deque[dict] = deque(maxlen=GECMIS)
_sonraki_id = 1


def yayinla(tur: str, **veri) -> int:
    """Bir olayı yayınla ve bekleyen istemcileri uyandır."""
    global _sonraki_id
    with _kilit:
        olay = {"id": _sonraki_id, "tur": tur, "zaman": time.time(), **veri}
        _olaylar.append(olay)
        _sonraki_id += 1
        _kilit.notify_all()
        return olay["id"]


def son_id() -> int:
    with _kilit:
        return _sonraki_id - 1


def bekle(since: int, bekleme: float = BEKLEME) -> dict:
    """``since`` sonrası olayları döndür; yoksa yeni olay gelene kadar bekle."""
    bitis = time.time() + bekleme
    with _kilit:
        while True:
            yeni = [o for o in _olaylar if o["id"] > since]
            if yeni:
                return {"olaylar": yeni, "son_id": _sonraki_id - 1}

            # İstemci çok geride kaldıysa (olaylar taşmışsa) tam yenileme iste.
            if _olaylar and since < _olaylar[0]["id"] - 1:
                return {"olaylar": [], "son_id": _sonraki_id - 1, "sifirla": True}

            kalan = bitis - time.time()
            if kalan <= 0:
                return {"olaylar": [], "son_id": _sonraki_id - 1}
            _kilit.wait(kalan)
