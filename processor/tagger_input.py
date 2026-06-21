import awkward as ak

def get_pfcands_features(events_after_preselection, jet_idx):
    """
    Extracts PFCands matched to the jet at index 'jet_idx'.
    jet_idx: result of an argmax/argmin (indices into the original FatJet collection)
    """
    # The mapping table provided by NanoAOD
    mapping = events_after_preselection.FatJetPFCands

    # Match the jet index. jet_idx is likely (Events, 1),
    # so we compare it to the mapping.jetIdx
    pfcand_mask = (mapping.jetIdx == jet_idx)

    # Get the indices of the PFCands and pull from global collection
    pfcand_indices = mapping.pFCandsIdx[pfcand_mask]
    matched_pfcands = events_after_preselection.PFCands[pfcand_indices]

    print(matched_pfcands.pt)

    return matched_pfcands