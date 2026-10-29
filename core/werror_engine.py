"""
Werror Engine (Orbital Error Dynamics & Chaos Decision Core)
===========================================================
Werrealm Bilişsel Yığınında (Cognitive Stack) Fraktal Kaos, Karar ve Bizans Bağışıklığı Motoru.

Teorik Temel:
- WERR (Waves & Errors) / Orbital Error Dynamics (OED, arXiv:2609.25498)
- Mandelbrot kaos sınırı (∂M) kaçış yörüngesi analizi ile 0-VRAM System-1 refleks kararları.
- Konsensüs düzeyinde "Epistemic Slashing": Ağdaki düğümlerin ve orakıl beslemelerinin
  hata sapmalarını (divergence metric) milisaniyelik seviyede ölçen bağışıklık kalkanı.
"""

import math
from typing import Tuple, Dict, Any
import os, sys

try:
    from core.werrite_engine import WerriteEngine
except ModuleNotFoundError:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.werrite_engine import WerriteEngine

class WerrorEngine:
    VERSION = "v1.0.0-Werror-OED-Core"
    
    # Fraktal Kaos Sabitleri (Q16.16 Paritesi)
    ESCAPE_RADIUS_SQ = WerriteEngine.to_fp(4.0)  # |z|^2 > 4.0 kaçış eşiği
    MAX_ITERATIONS = 36                          # Drosophila biyolojik vuruş penceresi

    def __init__(self):
        self.werrite = WerriteEngine()

    def evaluate_saccade(self, sensory_input_x: float, sensory_input_y: float) -> Dict[str, Any]:
        """
        Duyusal girdiyi (fiyat, volatilite, sorgu parametresi) Mandelbrot karmaşık koordinatına
        (c = cx + i*cy) dönüştürür ve kaçış dinamiğini (OED yörüngesini) hesaplar.
        0 Byte VRAM tüketir, tamamen deterministiktir.
        """
        cx_fp = WerriteEngine.to_fp(sensory_input_x)
        cy_fp = WerriteEngine.to_fp(sensory_input_y)

        zx_fp = 0
        zy_fp = 0
        escaped = False
        escape_step = self.MAX_ITERATIONS
        orbit_energy = 0

        for step in range(1, self.MAX_ITERATIONS + 1):
            zx_fp, zy_fp, mag2 = WerriteEngine.mandelbrot_step(zx_fp, zy_fp, cx_fp, cy_fp)
            orbit_energy += mag2 >> 16

            if mag2 > self.ESCAPE_RADIUS_SQ:
                escaped = True
                escape_step = step
                break

        # Karar Yönü: Yörüngenin Reel/İmajiner eksendeki asimetrisinden türetilir
        decision_direction = 1 if zx_fp >= 0 else -1
        stability_index = 1.0 - (escape_step / float(self.MAX_ITERATIONS))

        return {
            "escaped": escaped,
            "escape_step": escape_step,
            "decision_direction": decision_direction,
            "stability_index": round(stability_index, 4),
            "orbit_energy_fp": orbit_energy,
            "q16_state": {"zx": zx_fp, "zy": zy_fp, "cx": cx_fp, "cy": cy_fp}
        }

    def measure_byzantine_divergence(self, expected_state: Dict[str, Any], candidate_state: Dict[str, Any]) -> float:
        """
        Doğrulayıcı düğümün veya harici orakılın bildirdiği durum ile
        Werror deterministik durumu arasındaki sapmayı (hata metriğini) hesaplar.
        Sapma > 0.05 ise Bizans Hata Kalkanı (Epistemic Slashing) devreye girer.
        """
        exp_dir = expected_state.get("decision_direction", 0)
        cand_dir = candidate_state.get("decision_direction", 0)
        
        if exp_dir != cand_dir:
            return 1.0  # Tam aykırılık / Slashing
            
        exp_step = expected_state.get("escape_step", 0)
        cand_step = candidate_state.get("escape_step", 0)
        
        diff = abs(exp_step - cand_step)
        divergence = diff / float(self.MAX_ITERATIONS)
        return round(divergence, 4)

if __name__ == "__main__":
    engine = WerrorEngine()
    print(f"[*] {WerrorEngine.VERSION} Başlatıldı.")
    
    # Örnek piyasa duyusal girdisi: ETH yön değişimi ve volatilite şoku
    res = engine.evaluate_saccade(-0.7436438870371587, 0.13182590420531197)
    print(f"[*] Saccade Karar Testi: Kaçış={res['escaped']}, Adım={res['escape_step']}, Yön={res['decision_direction']}")
