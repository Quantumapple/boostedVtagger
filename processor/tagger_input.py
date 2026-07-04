import awkward as ak
import numpy as np

def get_pfcands_features(events_after_preselection, jet_idx):
    """
    Extracts PFCands matched to the jet at index 'jet_idx'.
    jet_idx: result of an argmax/argmin (indices into the original FatJet collection)
    """

    pfcands_dict = {}

    # The mapping table provided by NanoAOD
    mapping = events_after_preselection.FatJetPFCands

    # Match the jet index. jet_idx is likely (Events, 1),
    # so we compare it to the mapping.jetIdx
    pfcand_mask = (mapping.jetIdx == jet_idx)

    # Get the indices of the PFCands and pull from global collection
    pfcand_indices = mapping.pFCandsIdx[pfcand_mask]
    matched_pfcands = events_after_preselection.PFCands[pfcand_indices]

    # btag/impact-parameter features are jet-relative, so they live on the
    # FatJetPFCands mapping table itself, not on the global PFCands collection.
    btag_etarel = mapping.btagEtaRel[pfcand_mask]
    btag_ptratio = mapping.btagPtRatio[pfcand_mask]
    btag_pparratio = mapping.btagPParRatio[pfcand_mask]
    btag_sip3dval = mapping.btagSip3dVal[pfcand_mask]
    btag_sip3dsig = mapping.btagSip3dSig[pfcand_mask]
    btag_jetdistval = mapping.btagJetDistVal[pfcand_mask]

    # SORTING: Sort particles by descending pT within each jet
    pfcand_sort_idx = ak.argsort(matched_pfcands.pt, ascending=False)
    matched_pfcands = matched_pfcands[pfcand_sort_idx]
    btag_etarel = btag_etarel[pfcand_sort_idx]
    btag_ptratio = btag_ptratio[pfcand_sort_idx]
    btag_pparratio = btag_pparratio[pfcand_sort_idx]
    btag_sip3dval = btag_sip3dval[pfcand_sort_idx]
    btag_sip3dsig = btag_sip3dsig[pfcand_sort_idx]
    btag_jetdistval = btag_jetdistval[pfcand_sort_idx]

    leadingfj = ak.firsts(events_after_preselection.FatJet[jet_idx])

    pdgIds = matched_pfcands.pdgId
    pfcands_dict['pfcands_isEl'] = np.abs(pdgIds) == 11
    pfcands_dict['pfcands_isMu'] = np.abs(pdgIds) == 13
    pfcands_dict['pfcands_isChargedHad'] = np.abs(pdgIds) == 211
    pfcands_dict['pfcands_isGamma'] = np.abs(pdgIds) == 22
    pfcands_dict['pfcands_isNeutralHad'] = np.abs(pdgIds) == 130

    pfcands_dict['pfcands_px'] = matched_pfcands.px
    pfcands_dict['pfcands_py'] = matched_pfcands.py
    pfcands_dict['pfcands_pz'] = matched_pfcands.pz
    pfcands_dict['pfcands_energy'] = matched_pfcands.energy

    pfcands_dict['pfcands_logpt'] = np.log(matched_pfcands.pt)
    pfcands_dict['pfcands_loge'] = np.log(matched_pfcands.energy)
    pfcands_dict['pfcands_ptrel'] = matched_pfcands.pt/leadingfj.pt
    pfcands_dict['pfcands_logptrel'] = np.log(pfcands_dict['pfcands_ptrel'])
    pfcands_dict['pfcands_erel'] = matched_pfcands.energy/leadingfj.energy
    pfcands_dict['pfcands_logerel'] = np.log(pfcands_dict['pfcands_erel'])
    pfcands_dict['pfcands_charge'] = matched_pfcands.charge * 1.

    pfcands_dict['pfcands_dphi'] = leadingfj.delta_phi(matched_pfcands)
    raw_deta = matched_pfcands.eta - leadingfj.eta
    fj_etasign = ak.where(leadingfj.eta >= 0, 1, -1)
    pfcands_dict['pfcands_deta'] = raw_deta * fj_etasign
    pfcands_dict['pfcands_abseta'] = np.abs(matched_pfcands.eta)
    pfcands_dict['pfcands_dr'] = np.hypot(pfcands_dict['pfcands_dphi'], pfcands_dict['pfcands_deta'])

    pfcands_dict['pfcands_d0'] = matched_pfcands.d0
    pfcands_dict['pfcands_dz'] = matched_pfcands.dz
    pfcands_dict['pfcands_d0sig'] = matched_pfcands.d0 / matched_pfcands.d0Err
    pfcands_dict['pfcands_dzsig'] = matched_pfcands.dz / matched_pfcands.dzErr

    pfcands_dict["pfcands_VTXass"] = matched_pfcands.pvAssocQuality * 1.
    pfcands_dict["pfcands_lostInnerHits"] = matched_pfcands.lostInnerHits * 1.
    pfcands_dict["pfcands_quality"] = matched_pfcands.trkQuality * 1.
    pfcands_dict["pfcands_normchi2"] = np.floor(matched_pfcands.trkChi2) * 1.

    pfcands_dict["pfcands_btagEtaRel"] = btag_etarel
    pfcands_dict["pfcands_btagPtRatio"] = btag_ptratio
    pfcands_dict["pfcands_btagPParRatio"] = btag_pparratio
    pfcands_dict["pfcands_btagSip3dVal"] = btag_sip3dval
    pfcands_dict["pfcands_btagSip3dSig"] = btag_sip3dsig
    pfcands_dict["pfcands_btagJetDistVal"] = btag_jetdistval

    return pfcands_dict

def get_svs_features(events_after_preselection, jet_idx):

    svs_dict = {}

    # 1. Get the Jet Object for relative calculations
    leadingfj = ak.firsts(events_after_preselection.FatJet[jet_idx])

    # 2. Match and Extract SVs using the mapping table
    # mapping table: FatJetSVs (jetIdx -> sVIdx)
    mapping = events_after_preselection.FatJetSVs

    # Mask to find SVs belonging to our leading_fj_idx
    sv_mask = (mapping.jetIdx == jet_idx) & (mapping.sVIdx != -1)

    # Extract the actual SV objects from the global SV collection
    matched_svs = events_after_preselection.SV[mapping.sVIdx[sv_mask]]

    # 3. SORTING: SVs are almost always sorted by dxySig (Displacement Significance)
    # This helps the AI see the most 'displaced' (likely B/C decay) vertices first.
    sv_sort_idx = ak.argsort(matched_svs.dxySig, ascending=False)
    matched_svs = matched_svs[sv_sort_idx]

    # SecondaryVertex doesn't expose delta_phi() on its top-level record (only its
    # nested .p4 sub-record has full vector behavior), so compute the wrapped
    # difference manually instead. Matches the pfcand convention: jet.phi - obj.phi,
    # wrapped to [-pi, pi], confirmed consistent with GloParT's training-time formula.
    raw_dphi = leadingfj.phi - matched_svs.phi
    svs_dict['sv_dphi'] = (raw_dphi + np.pi) % (2 * np.pi) - np.pi
    # sign by the jet's own eta (matches pfcand_deta and GloParT's training-time formula)
    sv_etasign = ak.where(leadingfj.eta >= 0, 1, -1)
    svs_dict['sv_deta'] = sv_etasign * (matched_svs.eta - leadingfj.eta)
    svs_dict['sv_abseta'] = np.abs(matched_svs.eta)
    svs_dict["sv_mass"] = matched_svs.mass
    svs_dict["sv_pt_log"] = np.log(matched_svs.pt)

    svs_dict["sv_ntracks"] = matched_svs.ntracks
    svs_dict["sv_normchi2"] = matched_svs.chi2
    svs_dict["sv_dxy"] = matched_svs.dxy
    svs_dict["sv_dxysig"] = matched_svs.dxySig
    svs_dict["sv_d3d"] = matched_svs.dlen
    svs_dict["sv_d3dsig"] = matched_svs.dlenSig
    svs_dict["sv_costhetasvpv"] = -np.cos(matched_svs.pAngle)

    # SecondaryVertex has no top-level px/py/pz/energy fields (unlike PFCand);
    # only its nested .p4 sub-record exposes the Lorentz vector components.
    svs_dict["sv_px"] = matched_svs.p4.px
    svs_dict["sv_py"] = matched_svs.p4.py
    svs_dict["sv_pz"] = matched_svs.p4.pz
    svs_dict["sv_energy"] = matched_svs.p4.energy

    return svs_dict
