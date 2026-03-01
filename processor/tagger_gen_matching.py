from __future__ import annotations

import awkward as ak
import numpy as np
from coffea.nanoevents.methods.base import NanoEventsArray
from coffea.nanoevents.methods.nanoaod import FatJetArray, GenParticleArray

d_PDGID = 1
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

    # Find the closest boson to the fat jet.
    matched_vs = vs[ak.argmin(fatjet.delta_r(vs), axis=1, keepdims=True)]

    # Get the decay products of the matched boson
    daughters = ak.flatten(matched_vs.distinctChildren, axis=2)
    daughters = daughters[daughters.hasFlags(["fromHardProcess", "isLastCopy"])]
    daughters_pdgId = abs(daughters.pdgId)

    # Hadronic decay: exactly 2 quarks (excluding b quarks)
    is_2q = ak.sum(daughters_pdgId < b_PDGID, axis=1) == 2

    # Exclude neutrinos for prong counting
    neutrino_mask = (
        (daughters_pdgId != vELE_PDGID)
        & (daughters_pdgId != vMU_PDGID)
        & (daughters_pdgId != vTAU_PDGID)
    )
    daughters_nov = daughters[neutrino_mask]
    daughters_nov_pdgId = daughters_pdgId[neutrino_mask]

    # Cache delta_r for daughters_nov
    dr_daughters_nov = fatjet.delta_r(daughters_nov)
    nprongs = ak.sum(dr_daughters_nov < JET_DR, axis=1)
    both_quarks_in_cone = (nprongs == 2)

    # c quarks — reuse already-masked pdgId array
    cquarks = daughters_nov[daughters_nov_pdgId == c_PDGID]
    ncquarks = ak.sum(fatjet.delta_r(cquarks) < JET_DR, axis=1)

    # Final matching: hadronic decay + both quarks captured in jet
    matched_mask = both_quarks_in_cone & is_2q

    p = f"fj_is{label}"
    genVars = {
        f"{p}_Matched": matched_mask,
        f"{p}_2q": is_2q,
        f"fj_{label}_nprongs": nprongs,
        f"fj_{label}_ncquarks": ncquarks,
    }

    return genVars, matched_mask


def match_Z(genparts: GenParticleArray, fatjet: FatJetArray):
    """Gen matching for Z boson."""
    return _match_boson(genparts, fatjet, boson_pdgid=Z_PDGID, use_sign=False, label="Z")


def match_Wplus(genparts: GenParticleArray, fatjet: FatJetArray):
    """Gen matching for W+ boson (pdgId = +24)."""
    return _match_boson(genparts, fatjet, boson_pdgid=W_PDGID, use_sign=True, positive=True, label="Wplus")


def match_Wminus(genparts: GenParticleArray, fatjet: FatJetArray):
    """Gen matching for W- boson (pdgId = -24)."""
    return _match_boson(genparts, fatjet, boson_pdgid=W_PDGID, use_sign=True, positive=False, label="Wminus")


def match_QCD(
    genparts: GenParticleArray, fatjets: FatJetArray
) -> tuple[np.array, dict[str, np.array]]:
    """Gen matching for QCD samples, arguments as defined in `tagger_gen_matching`."""

    partons = genparts[
        get_pid_mask(
            genparts, [g_PDGID] + list(range(1, b_PDGID + 1)), ax=1, byall=False
        )
    ]
    matched_mask = ak.any(fatjets.delta_r(partons) < JET_DR, axis=1)

    genVars = {
        "fj_isQCD_Matched": matched_mask,
        "fj_isQCDb": (fatjets.nBHadrons == 1),
        "fj_isQCDbb": (fatjets.nBHadrons > 1),
        "fj_isQCDc": (fatjets.nCHadrons == 1) * (fatjets.nBHadrons == 0),
        "fj_isQCDcc": (fatjets.nCHadrons > 1) * (fatjets.nBHadrons == 0),
        "fj_isQCDothers": (fatjets.nBHadrons == 0) & (fatjets.nCHadrons == 0),
    }

    return genVars, matched_mask


def get_genjet_vars(events: NanoEventsArray, fatjets: FatJetArray):
    """Matched fat jet to gen-level jet and gets gen jet vars"""
    GenJetVars = {}

    # NanoAOD automatically matched ak8 fat jets
    # No soft dropped gen jets however
    GenJetVars["fj_genjetmass"] = fatjets.matched_gen.mass
    matched_gen_jet_mask = np.ones(len(events), dtype="bool")

    return GenJetVars, matched_gen_jet_mask