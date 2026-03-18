from __future__ import annotations

import awkward as ak
import numpy as np
from coffea.nanoevents.methods.base import NanoEventsArray
from coffea.nanoevents.methods.nanoaod import FatJetArray, GenParticleArray

d_PDGID = 1
u_PDGID = 2
s_PDGID = 3
c_PDGID = 4
b_PDGID = 5
g_PDGID = 21
TOP_PDGID = 6

ELE_PDGID = 11
vELE_PDGID = 12
MU_PDGID = 13
vMU_PDGID = 14
TAU_PDGID = 15
vTAU_PDGID = 16

GAMMA_PDGID = 22
Z_PDGID = 23
W_PDGID = 24
HIGGS_PDGID = 25

PI_PDGID = 211
PO_PDGID = 221
PP_PDGID = 111

GEN_FLAGS = ["fromHardProcess", "isLastCopy"]

FILL_NONE_VALUE = -99999

JET_DR = 0.8


def get_pid_mask(
    genparts: GenParticleArray,
    pdgids: int | list,
    ax: int = 2,
    byall: bool = True,
) -> ak.Array:
    """
    Get selection mask for gen particles matching any of the pdgIds in ``pdgids``.
    If ``byall``, checks all particles along axis ``ax`` match.
    """
    gen_pdgids = abs(genparts.pdgId)
    pdgids = [pdgids] if not isinstance(pdgids, list) else pdgids
    mask = ak.zeros_like(gen_pdgids, dtype=bool)
    for pdgid in pdgids:
        mask = mask | (gen_pdgids == pdgid)
    return ak.all(mask, axis=ax) if byall else mask

def _match_boson(
    genparts: GenParticleArray,
    fatjet: FatJetArray,
    boson_pdgid: int,
    use_sign: bool = False,
    positive: bool = True,
    label: str = "V",
):
    """
    Core boson matching logic. Shared by match_Z, match_Wplus, match_Wminus.
    Targets hadronic decays only (V -> qq).

    Args:
        boson_pdgid: PDG ID to match (e.g. Z_PDGID, W_PDGID)
        use_sign:    If True, match by signed pdgId (to distinguish W+ vs W-)
        positive:    If use_sign=True, match pdgId > 0 (W+) or < 0 (W-)
        label:       Prefix for output keys e.g. "Z", "Wplus", "Wminus"
    """
    if use_sign:
        sign_mask = (genparts.pdgId == boson_pdgid) if positive else (genparts.pdgId == -boson_pdgid)
        vs = genparts[sign_mask * genparts.hasFlags(GEN_FLAGS)]
    else:
        vs = genparts[
            get_pid_mask(genparts, boson_pdgid, byall=False)
            * genparts.hasFlags(GEN_FLAGS)
        ]

    # Find the closest boson to the fat jet
    matched_vs = vs[ak.argmin(fatjet.delta_r(vs), axis=1, keepdims=True)]

    # Get the decay products of the matched boson
    daughters = ak.flatten(matched_vs.distinctChildren, axis=2)
    daughters = daughters[daughters.hasFlags(["fromHardProcess", "isLastCopy"])]
    daughters_pdgId = abs(daughters.pdgId)

    # =========== Hadronic decay requirement ===========
    if label in ["Wplus", "Wminus"]:
        # W: exactly 2 light quarks (u, d, s, c — excluding b)
        is_2q = ak.sum(daughters_pdgId < b_PDGID, axis=1) == 2
    else:
        # Z: exactly 2 quarks (u, d, s, c, b — including b for Z->bb)
        is_2q = ak.sum(daughters_pdgId <= b_PDGID, axis=1) == 2

    # =========== Decay mode separation ===========
    if label in ["Wplus", "Wminus"]:
        # W -> ud: one u quark and one d quark
        is_ud = (
            (ak.sum(daughters_pdgId == u_PDGID, axis=1) == 1)
            & (ak.sum(daughters_pdgId == d_PDGID, axis=1) == 1)
        )
        # W -> cs: one c quark and one s quark
        is_cs = (
            (ak.sum(daughters_pdgId == c_PDGID, axis=1) == 1)
            & (ak.sum(daughters_pdgId == s_PDGID, axis=1) == 1)
        )
    else:
        # Z -> bb: two b quarks
        is_bb = ak.sum(daughters_pdgId == b_PDGID, axis=1) == 2
        # Z -> cc: two c quarks
        is_cc = ak.sum(daughters_pdgId == c_PDGID, axis=1) == 2
        # Z -> qq: light quarks (u, d, s) or gluon
        is_qq = (
            (ak.sum(daughters_pdgId == u_PDGID, axis=1) >= 1)
            | (ak.sum(daughters_pdgId == d_PDGID, axis=1) >= 1)
            | (ak.sum(daughters_pdgId == s_PDGID, axis=1) >= 1)
            | (ak.sum(daughters_pdgId == g_PDGID, axis=1) >= 1)
        )

    # Neutrino mask — no-op for hadronic decays but kept as safety check
    # against unexpected gen-level particles in the decay tree
    neutrino_mask = (
        (daughters_pdgId != vELE_PDGID)
        & (daughters_pdgId != vMU_PDGID)
        & (daughters_pdgId != vTAU_PDGID)
    )
    daughters_nov = daughters[neutrino_mask]
    daughters_nov_pdgId = daughters_pdgId[neutrino_mask]

    # Prong counting — reuse for both_quarks_in_cone
    dr_daughters_nov = fatjet.delta_r(daughters_nov)
    nprongs = ak.sum(dr_daughters_nov < JET_DR, axis=1)
    both_quarks_in_cone = nprongs == 2

    # c quarks — reuse already-masked pdgId array
    cquarks = daughters_nov[daughters_nov_pdgId == c_PDGID]
    ncquarks = ak.sum(fatjet.delta_r(cquarks) < JET_DR, axis=1)

    # Final matching: fully merged hadronic decay
    matched_mask = is_2q & both_quarks_in_cone

    p = f"fj_is{label}"
    genVars = {
        f"{p}_Matched": matched_mask,
        f"{p}_2q": is_2q & matched_mask,  # combined flag kept for convenience
        f"fj_{label}_nprongs": nprongs,
        f"fj_{label}_ncquarks": ncquarks,
    }

    # Add decay mode specific flags
    if label in ["Wplus", "Wminus"]:
        genVars[f"{p}_ud"] = is_ud & matched_mask
        genVars[f"{p}_cs"] = is_cs & matched_mask
    else:
        # Z boson decay modes
        genVars[f"{p}_bb"] = is_bb & matched_mask
        genVars[f"{p}_cc"] = is_cc & matched_mask
        genVars[f"{p}_qq"] = is_qq & matched_mask

    return genVars, matched_mask


def match_Z(genparts: GenParticleArray, fatjet: FatJetArray):
    """Gen matching for Z boson (pdgId = 23)."""
    return _match_boson(genparts, fatjet, boson_pdgid=Z_PDGID, use_sign=False, label="Z")


def match_Wplus(genparts: GenParticleArray, fatjet: FatJetArray):
    """Gen matching for W+ boson (pdgId = +24)."""
    return _match_boson(genparts, fatjet, boson_pdgid=W_PDGID, use_sign=True, positive=True, label="Wplus")


def match_Wminus(genparts: GenParticleArray, fatjet: FatJetArray):
    """Gen matching for W- boson (pdgId = -24)."""
    return _match_boson(genparts, fatjet, boson_pdgid=W_PDGID, use_sign=True, positive=False, label="Wminus")


def match_QCD(genparts: GenParticleArray, fatjet: FatJetArray) -> tuple[np.array, dict[str, np.array]]:
    """
    Gen matching for QCD samples.
    A jet is considered QCD if it is not matched to any heavy object (W, Z, H, Top)
    within JET_DR. No subcategories needed — QCD is QCD.
    """

    # Check if any heavy boson is within JET_DR of the fat jet
    heavy_objects = genparts[
        get_pid_mask(genparts, [W_PDGID, Z_PDGID, HIGGS_PDGID, TOP_PDGID], byall=False)
        * genparts.hasFlags(GEN_FLAGS)
    ]

    # QCD jet = no heavy object found nearby
    dr_heavy = fatjet.delta_r(heavy_objects)
    matched_mask = ~ak.any(dr_heavy < JET_DR, axis=1)

    genVars = {
        "fj_isQCD_Matched": matched_mask,
    }

    return genVars, matched_mask