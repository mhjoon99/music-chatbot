import numpy as np
import pandas as pd

def build_iso_playlist(df: pd.DataFrame, track_ids: list, current_valence: float,
                       target_valence: float, steps: int = 5,
                       current_energy: float = None, target_energy: float = None) -> dict:
    """동질 원리에 따라 곡 순서 배열 (현재 감정 → 목표 감정)"""
    candidates = df[df["track_id"].isin(track_ids)].copy()
    # 현재 valence에서 목표 valence까지 균등 분할
    valence_targets = np.linspace(current_valence, target_valence, steps)

    use_energy = current_energy is not None and target_energy is not None
    if use_energy:
        energy_targets = np.linspace(current_energy, target_energy, steps)

    playlist = []
    used_ids = set()

    for i, target_v in enumerate(valence_targets):
        # 아직 사용하지 않은 후보 중 현재 단계 목표에 가장 가까운 곡 선택
        remaining = candidates[~candidates["track_id"].isin(used_ids)]
        if remaining.empty:
            break
        if use_energy:
            target_e = energy_targets[i]
            dist = np.sqrt((remaining["valence"] - target_v) ** 2 + (remaining["energy"] - target_e) ** 2)
            closest_idx = dist.idxmin()
        else:
            closest_idx = (remaining["valence"] - target_v).abs().idxmin()
        selected = remaining.loc[closest_idx]
        explanation = (
            f"valence {selected['valence']:.2f}/energy {selected['energy']:.2f} → 목표 v={target_v:.2f}/e={energy_targets[i]:.2f} 단계"
            if use_energy else
            f"valence {selected['valence']:.2f} → 목표 {target_v:.2f} 단계"
        )
        playlist.append({
            "track_id": selected["track_id"],
            "track_name": selected["track_name"],
            "track_artist": selected["track_artist"],
            "valence": float(selected["valence"]),
            "energy": float(selected["energy"]),
            "target_valence_step": float(target_v),
            "iso_explanation": explanation
        })
        used_ids.add(selected["track_id"])

    return {
        "playlist": playlist,
        "iso_applied": True,
        "direction": "ascending" if target_valence > current_valence else "descending"
    }
