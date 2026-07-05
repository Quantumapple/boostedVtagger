import argparse

import awkward as ak
import numpy as np
import matplotlib.pyplot as plt
import mplhep as hep

hep.style.use('CMS')

CLASS_NAMES = ['Wplus', 'Wminus', 'Z']
COLORS = ['#5790fc', '#e42536', '#964a8b']


def _roc_curve(y_true, y_score):
    order = np.argsort(-y_score)
    y_true = y_true[order]
    tps = np.concatenate(([0], np.cumsum(y_true)))
    fps = np.concatenate(([0], np.cumsum(1 - y_true)))
    tpr = tps / tps[-1]
    fpr = fps / fps[-1]
    trapezoid = getattr(np, 'trapezoid', None) or np.trapz
    auc = trapezoid(tpr, fpr)
    return fpr, tpr, auc


def plot_confusion_matrix(labels, preds, output):
    n = len(CLASS_NAMES)
    cm = np.zeros((n, n), dtype=int)
    for t, p in zip(labels, preds):
        cm[t, p] += 1
    cm_norm = cm / cm.sum(axis=1, keepdims=True)

    fig, ax = plt.subplots(figsize=(9, 8))
    im = ax.imshow(cm_norm, cmap='Blues', vmin=0, vmax=1)
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(CLASS_NAMES)
    ax.set_yticklabels(CLASS_NAMES)
    ax.set_xlabel('Predicted class')
    ax.set_ylabel('True class')
    for i in range(n):
        for j in range(n):
            ax.text(j, i, f'{cm_norm[i, j]:.2f}\n({cm[i, j]})', ha='center', va='center',
                    color='white' if cm_norm[i, j] > 0.5 else 'black', fontsize=14)
    fig.colorbar(im, ax=ax, label='Row-normalized fraction (recall)')
    hep.cms.label('Preliminary', ax=ax, fontsize=18, rlabel='', loc=0)
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close(fig)
    print(f'Saved {output}')


def plot_roc_curves(labels, scores, output):
    fig, ax = plt.subplots(figsize=(7, 6.5))
    for i, name in enumerate(CLASS_NAMES):
        y_true = (labels == i).astype(int)
        fpr, tpr, auc = _roc_curve(y_true, scores[:, i])
        ax.plot(fpr, tpr, color=COLORS[i], label=f'{name} (AUC = {auc:.3f})')
    ax.plot([0, 1], [0, 1], color='gray', linestyle='--', linewidth=1)
    ax.set_xlabel('False positive rate')
    ax.set_ylabel('True positive rate')
    ax.legend(loc='lower right', fontsize=16)
    hep.cms.label('Preliminary', ax=ax, fontsize=18, rlabel='')
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close(fig)
    print(f'Saved {output}')


def plot_score_distributions(labels, scores, output):
    fig, axes = plt.subplots(1, 3, figsize=(18, 6), sharey=True)
    bins = np.linspace(0, 1, 31)
    for i, (ax, name) in enumerate(zip(axes, CLASS_NAMES)):
        for j, true_name in enumerate(CLASS_NAMES):
            mask = labels == j
            ax.hist(scores[mask, i], bins=bins, histtype='step', linewidth=2,
                    color=COLORS[j], label=f'True {true_name}', density=True)
        ax.set_xlabel(f'{name} score')
        if i == 0:
            ax.set_ylabel('Normalized entries')
        ax.legend(fontsize=14)
        hep.cms.label('Preliminary', ax=ax, fontsize=16, rlabel='')
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close(fig)
    print(f'Saved {output}')


def main():
    parser = argparse.ArgumentParser(description='Confusion matrix, per-class ROC/AUC, and score '
                                      'distribution plots from a weaver --predict output parquet.')
    parser.add_argument('--input_parquet')
    parser.add_argument('--output-prefix', default='test_diagnostics')
    args = parser.parse_args()

    arr = ak.from_parquet(args.input_parquet)
    labels = ak.to_numpy(arr['_label_'])
    scores = ak.to_numpy(arr['scores'])
    preds = scores.argmax(axis=1)

    plot_confusion_matrix(labels, preds, f'{args.output_prefix}_confusion_matrix.png')
    plot_roc_curves(labels, scores, f'{args.output_prefix}_roc_curves.png')
    plot_score_distributions(labels, scores, f'{args.output_prefix}_score_distributions.png')

    acc = (preds == labels).mean()
    print(f'Overall accuracy: {acc:.5f}')


if __name__ == '__main__':
    main()
