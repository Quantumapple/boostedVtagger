"""
Identify AK8 jets that originate from the Higgs in WH/ZH samples.

In WH/ZH (H -> WW) samples the hard-process V (W or Z -> qq) is the signal,
but the W's from the Higgs decay also carry ``fromHardProcess`` and
``isLastCopy`` and would be picked up by the existing V gen matching in
``tagger_gen_matching.py``. This module is meant to run BEFORE the leading-jet
selection: jets flagged here are removed from the AK8 candidate list, so the
leading jet becomes the leading non-Higgs jet (normally the V jet) and the
existing ``match_*`` functions can be used unchanged.

Truth structure (checked on ZH-Zto2Q-Hto2WtoLNu2Q):
  - hard-process V (last copy): mother is another V copy -> never a Higgs child
  - W from H -> WW: fromHardProcess + isLastCopy, mother is the last-copy Higgs
"""
from __future__ import annotations

import awkward as ak
import numpy as np
from coffea.nanoevents.methods.nanoaod import FatJetArray, GenParticleArray

Z_PDGID = 23
W_PDGID = 24
HIGGS_PDGID = 25
B_PDGID = 5

GEN_FLAGS = ["fromHardProcess", "isLastCopy"]

JET_DR = 0.8


def _min_dr(fatjets: FatJetArray, objs: GenParticleArray) -> ak.Array:
    """Per-jet minimum ΔR to ``objs``; inf where the event has no such object."""
    dr = fatjets.metric_table(objs)  # (event, jet, obj)
    return ak.min(dr, axis=-1, initial=np.inf, mask_identity=False)


def from_higgs_jet_mask(
    genparts: GenParticleArray,
    fatjets: FatJetArray,
    jet_dr: float = JET_DR,
) -> ak.Array:
    """
    Boolean mask per AK8 jet (same jagged shape as ``fatjets``): True if the
    jet comes from the Higgs and should be removed.

    A jet is "from H" if it lies within ``jet_dr`` of an H-origin gen object
    AND is closer to it than to the true hard-process V (so a V jet sitting
    next to the Higgs is not removed).

    H-origin objects:
      - the last-copy Higgs
      - W/Z (fromHardProcess, isLastCopy) whose distinctParent is a Higgs
      - the quark/gluon daughters of those W/Z
    Hard-process V: W/Z (fromHardProcess, isLastCopy) whose parent is not a Higgs.
    """
    higgs = genparts[(genparts.pdgId == HIGGS_PDGID) & genparts.hasFlags(["isLastCopy"])]

    vs = genparts[
        ((abs(genparts.pdgId) == W_PDGID) | (abs(genparts.pdgId) == Z_PDGID))
        & genparts.hasFlags(GEN_FLAGS)
    ]
    parent_pdgid = ak.fill_none(vs.distinctParent.pdgId, 0)
    v_from_h = vs[parent_pdgid == HIGGS_PDGID]
    v_hard = vs[parent_pdgid != HIGGS_PDGID]

    # quark/gluon daughters of the W/Z from the Higgs
    daughters = ak.flatten(v_from_h.distinctChildren, axis=2)
    daughters = daughters[
        daughters.hasFlags(GEN_FLAGS)
        & ((abs(daughters.pdgId) <= B_PDGID) | (abs(daughters.pdgId) == 21))
    ]

    dr_h = ak.min(
        ak.concatenate(
            [
                _min_dr(fatjets, higgs)[..., None],
                _min_dr(fatjets, v_from_h)[..., None],
                _min_dr(fatjets, daughters)[..., None],
            ],
            axis=-1,
        ),
        axis=-1,
    )
    dr_v = _min_dr(fatjets, v_hard)

    return (dr_h < jet_dr) & (dr_h < dr_v)
