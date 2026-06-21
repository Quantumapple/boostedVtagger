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

    # SORTING: Sort particles by descending pT within each jet
    pfcand_sort_idx = ak.argsort(matched_pfcands.pt, ascending=False)
    matched_pfcands = matched_pfcands[pfcand_sort_idx]

    leadingfj = ak.firsts(events_after_preselection.FatJet[jet_idx])

    pfcands_dict['pfcands_pdgId'] = matched_pfcands.pdgId * 1.
    pfcands_dict['pfcands_px'] = matched_pfcands.px
    pfcands_dict['pfcands_py'] = matched_pfcands.py
    pfcands_dict['pfcands_pz'] = matched_pfcands.pz

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
    pfcands_dict['pfcands_dr'] = np.hypot(pfcands_dict['pfcands_dphi'], pfcands_dict['pfcands_deta'])

    pfcands_dict['pfcands_d0'] = matched_pfcands.d0
    pfcands_dict['pfcands_dz'] = matched_pfcands.dz
    pfcands_dict['pfcands_d0sig'] = matched_pfcands.d0 / matched_pfcands.d0Err
    pfcands_dict['pfcands_dzsig'] = matched_pfcands.dz / matched_pfcands.dzErr

    return pfcands_dict