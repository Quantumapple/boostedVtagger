import argparse
import math

import awkward as ak
import numpy as np
import matplotlib.pyplot as plt
import mplhep as hep

hep.style.use('CMS')

DEFAULT_CLASS_NAMES = ['Wplus', 'Wminus', 'Z', 'QCD']
COLOR_PALETTE = ['#5790fc', '#e42536', '#964a8b', '#f89c20', '#9c9ca1', '#7a21dd']


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


def plot_confusion_matrix(labels, preds, output, class_names):
    n = len(class_names)
    cm = np.zeros((n, n), dtype=int)
    for t, p in zip(labels, preds):
        cm[t, p] += 1
    cm_norm = cm / cm.sum(axis=1, keepdims=True)

    fig, ax = plt.subplots(figsize=(max(6, 2.2 * n + 2), max(5.5, 2 * n + 2)))
    im = ax.imshow(cm_norm, cmap='Blues', vmin=0, vmax=1)
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(class_names)
    ax.set_yticklabels(class_names)
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


def plot_roc_curves(labels, scores, output, class_names, colors):
    fig, ax = plt.subplots(figsize=(7, 6.5))
    for i, name in enumerate(class_names):
        y_true = (labels == i).astype(int)
        fpr, tpr, auc = _roc_curve(y_true, scores[:, i])
        ax.plot(fpr, tpr, color=colors[i], label=f'{name} (AUC = {auc:.3f})')
    ax.plot([0, 1], [0, 1], color='gray', linestyle='--', linewidth=1)
    ax.set_xlabel('False positive rate')
    ax.set_ylabel('True positive rate')
    ax.legend(loc='lower right', fontsize=16)
    hep.cms.label('Preliminary', ax=ax, fontsize=18, rlabel='')
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close(fig)
    print(f'Saved {output}')


def plot_score_distributions(labels, scores, output, class_names, colors):
    n = len(class_names)
    ncols = 2 if n > 1 else 1
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 6 * nrows), sharey=True, squeeze=False)
    axes = axes.flatten()
    bins = np.linspace(0, 1, 31)
    for i, name in enumerate(class_names):
        ax = axes[i]
        for j, true_name in enumerate(class_names):
            mask = labels == j
            ax.hist(scores[mask, i], bins=bins, histtype='step', linewidth=2,
                    color=colors[j], label=f'True {true_name}', density=True)
        ax.set_xlabel(f'{name} score')
        if i % ncols == 0:
            ax.set_ylabel('Normalized entries')
        ax.legend(fontsize=14)
        hep.cms.label('Preliminary', ax=ax, fontsize=16, rlabel='')
    for i in range(n, len(axes)):
        axes[i].axis('off')
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close(fig)
    print(f'Saved {output}')


def main():
    parser = argparse.ArgumentParser(description='Confusion matrix, per-class ROC/AUC, and score '
                                      'distribution plots from a weaver --predict output parquet. '
                                      'Works for any number of classes (e.g. the 4-way Wplus/Wminus/'
                                      'Z/QCD tagger, or a 2-way binary stage like QCD-vs-V).')
    parser.add_argument('--input_parquet')
    parser.add_argument('--output-prefix', default='test_diagnostics')
    parser.add_argument('--class-names', default=None,
                         help='Comma-separated class names, in the same order as the yaml\'s '
                              '`labels.value` list (i.e. column order in `scores`). Defaults to '
                              'the 4-way Wplus,Wminus,Z,QCD tagger. Example for a binary stage: '
                              '--class-names V,QCD')
    args = parser.parse_args()

    class_names = args.class_names.split(',') if args.class_names else DEFAULT_CLASS_NAMES
    colors = COLOR_PALETTE[:len(class_names)]

    arr = ak.from_parquet(args.input_parquet)
    labels = ak.to_numpy(arr['_label_'])
    scores = ak.to_numpy(arr['scores'])
    preds = scores.argmax(axis=1)

    plot_confusion_matrix(labels, preds, f'{args.output_prefix}_confusion_matrix.png', class_names)
    plot_roc_curves(labels, scores, f'{args.output_prefix}_roc_curves.png', class_names, colors)
    plot_score_distributions(labels, scores, f'{args.output_prefix}_score_distributions.png', class_names, colors)

    acc = (preds == labels).mean()
    print(f'Overall accuracy: {acc:.5f}')


if __name__ == '__main__':
    main()