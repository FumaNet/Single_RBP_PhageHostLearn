import pandas as pd
import numpy as np
from sklearn.model_selection import LeaveOneGroupOut
from xgboost import XGBClassifier
from tqdm import tqdm
from sklearn.metrics import roc_auc_score, auc, roc_curve
import matplotlib.pyplot as plt
import os.path
import pickle


# Files Needed:
# Data/esm2_embeddings_loci_per_protein.csv
# Data/esm2_embeddings_rbp.csv
# Data/phage_host_interactions.csv
# grouping/grouping_1.pkl, _995, _990, _950, _985, _980, _975 (7 files total)
# Data/kaptive_results.tsv


predictions = []

if not os.path.isfile('Data/combined_embeddings_per_protein.csv'):
    print("Loading and preparing data from scratch...")

    # --- LOAD AND PREPARE DATA ---
    embeddings_loci_protein = pd.read_csv("Data/esm2_embeddings_loci_per_protein.csv")
    embeddings_rbp = pd.read_csv("Data/esm2_embeddings_rbp.csv")
    phage_host_interactions = pd.read_csv('Data/phage_host_interactions.csv')

    # Reshape the interaction matrix to get (host, phage, label) rows
    interactions_melted = phage_host_interactions.melt(
        id_vars=['Unnamed: 0'], var_name='phage_ID', value_name='label'
    ).rename(columns={'Unnamed: 0': 'accession'})

    # Remove NaN interactions
    interactions_melted = interactions_melted.dropna(subset=['label'])

    # Merge host embeddings with interaction pairs (per protein)
    merged = interactions_melted.merge(embeddings_loci_protein, on='accession', how='inner')
    merged = merged.merge(embeddings_rbp, on='phage_ID', how='inner')

    # Select host and virus embedding columns
    host_embedding_cols = [col for col in merged.columns if col not in ['accession', 'phage_ID', 'protein_index', 'protein_ID', 'label'] and '_x' in col]
    virus_embedding_cols = [col for col in merged.columns if col not in ['accession', 'phage_ID', 'protein_index', 'protein_ID', 'label'] and '_y' in col]

    host_embeddings = merged[host_embedding_cols].astype(np.float32)
    virus_embeddings = merged[virus_embedding_cols].astype(np.float32)

    host_embeddings.columns = [f"host_{i}" for i in range(host_embeddings.shape[1])]
    virus_embeddings.columns = [f"virus_{i}" for i in range(virus_embeddings.shape[1])]

    # Host protein embeddings included (no averaging upfront)
    final_df = pd.concat([
        merged[['accession', 'phage_ID', 'protein_index', 'protein_ID']],
        host_embeddings,
        virus_embeddings,
        merged[['label']]
    ], axis=1)

    final_df.to_csv('Data/combined_embeddings_per_protein.csv', index=False)
    print("Final per-protein dataframe saved as 'combined_embeddings_per_protein.csv'.")


else:
    print("Loading from existing 'combined_embeddings_per_protein.csv' file.")
    final_df = pd.read_csv('Data/combined_embeddings_per_protein.csv',
    dtype={'accession': str})
    print("Data loaded successfully.")


# --- MULTI-THRESHOLD LOGO CROSS-VALIDATION WITH MAX PROTEIN-PAIR SCORING ---
thresholds = [1.0, 0.995, 0.99, 0.95, 0.9, 0.85, 0.8, 0.75]
tstr = ['100', '99.5', '99', '95', '90', '85', '80', '75']

grouping_files = [
    "grouping/grouping_1.pkl",
    "grouping/grouping_995.pkl",
    "grouping/grouping_990.pkl",
    "grouping/grouping_950.pkl",
    "grouping/grouping_900.pkl",
    "grouping/grouping_850.pkl",
    "grouping/grouping_800.pkl",
    "grouping/grouping_750.pkl"
]



df_sero = pd.read_csv("Data/kaptive_results.tsv", sep="\t")

df_sero = df_sero[["Assembly", "Best match type", "Match confidence"]]



for i, threshold in enumerate(thresholds):

    with open(grouping_files[i], 'rb') as f:
        groups_dictionary = pickle.load(f)

    final_df['group_loci'] = final_df['accession'].map(groups_dictionary)

    logo = LeaveOneGroupOut()
    scores_max, label_max = [], []

    pbar = tqdm(total=len(set(final_df['group_loci'])), desc=f"LOGO CV @ {tstr[i]}%")

    for train_index, test_index in logo.split(final_df, final_df['label'], final_df['group_loci']):

        train_df = final_df.iloc[train_index].copy()
        test_df = final_df.iloc[test_index].copy()


        # Added: Serotype information, one-hot encoded
        # Removed: host protein embeddings 

        host_cols = [col for col in train_df.columns if col.startswith("host_")]
        train_df = train_df.drop(columns=host_cols)
        test_df = test_df.drop(columns=host_cols)

        # --- Merge serotype info ---
        print("Match Type != Typeable: ", len(df_sero[df_sero["Match confidence"] != "Typeable"]))
        print("Best match type == Capsule null: ", len(df_sero[df_sero["Best match type"] == "Capsule null"]))

        df_sero_filtered = df_sero.copy()

        # One-hot encode serotype
        one_hot_sero = pd.get_dummies(df_sero_filtered["Best match type"], prefix="sero_")
        df_sero_encoded = pd.concat([df_sero_filtered[["Assembly"]], one_hot_sero], axis=1)

        # Merge encoded serotype with training and test data
        train_df = train_df.merge(df_sero_encoded, how="left", left_on="accession", right_on="Assembly").drop(columns=["Assembly"])
        test_df = test_df.merge(df_sero_encoded, how="left", left_on="accession", right_on="Assembly").drop(columns=["Assembly"])

        # Fill any missing one-hot values with 0 (in case some accessions in test/train aren't in sero data)
        train_df.fillna(0, inplace=True)
        test_df.fillna(0, inplace=True)



        # Added
        train_df.drop_duplicates(inplace=True)
        test_df.drop_duplicates(inplace=True)


        # --- Feature and Label Extraction ---
        X_train = train_df[[col for col in train_df.columns if col.startswith(('sero_', 'virus_'))]].values
        y_train = train_df['label'].astype(int).values

        X_test = test_df[[col for col in test_df.columns if col.startswith(('sero_', 'virus_'))]].values
        y_test = test_df['label'].astype(int).values

        if len(set(y_train)) < 2:
            continue

        imbalance = sum(y_train == 1) / sum(y_train == 0) if sum(y_train == 0) else 1

        xgb = XGBClassifier(
            scale_pos_weight=1 / imbalance,
            learning_rate=0.3,
            n_estimators=250,
            max_depth=7,
            eval_metric='logloss',
            use_label_encoder=False,
            tree_method="gpu_hist",
            predictor="gpu_predictor",
            device="cuda"
        )
        xgb.fit(X_train, y_train)

        score_xgb = xgb.predict_proba(X_test)[:, 1]

        df_preds = pd.DataFrame({
            'accession': test_df['accession'],
            'phage_ID': test_df['phage_ID'],
            # 'protein_index': test_df['protein_index'], # remove if working with original, averaged embeddings
            'true_label': y_test,
            'score': score_xgb
        })

        # --- Aggregate Predictions (Max Score per Host-Phage Pair considering host proteins) ---
        max_scores = df_preds.groupby(['accession', 'phage_ID']).agg({
            'score': 'max',  # Max score across all host-virus protein pairs
            'true_label': 'first'
        }).reset_index()

        scores_max.append(max_scores['score'].values)
        label_max.append(max_scores['true_label'].values)
        pbar.update(1)

    pbar.close()

    scores_max = np.concatenate(scores_max)
    label_max = np.concatenate(label_max)

    if len(label_max) > 0 and len(set(label_max)) > 1:
        fpr, tpr, _ = roc_curve(label_max, scores_max)
        rauclr = round(auc(fpr, tpr), 3)
        print(f"Final AUC with max protein-pair scoring: {rauclr}")
        predictions.append((label_max, scores_max, rauclr))
    else:
        print(f"Final evaluation failed at {tstr[i]}% threshold due to single-class predictions.")


file_path = 'Results/3_AUCs_max_max_sero.pkl'

# --- Save (dump) the tuple into a pickle file ---
with open(file_path, 'wb') as f:
    pickle.dump(predictions, f)



# --- TRAIN A MODEL ON ALL DATA (NO VALIDATION) ---
print("\nTraining final model on the full dataset (no validation split)...")

# Prepare the serotype data again
df_sero_filtered = df_sero.copy()
one_hot_sero = pd.get_dummies(df_sero_filtered["Best match type"], prefix="sero_")
df_sero_encoded = pd.concat([df_sero_filtered[["Assembly"]], one_hot_sero], axis=1)

# Drop host protein embeddings
host_cols = [col for col in final_df.columns if col.startswith("host_")]
full_df = final_df.drop(columns=host_cols)

# Merge encoded serotype info
full_df = full_df.merge(df_sero_encoded, how="left", left_on="accession", right_on="Assembly").drop(columns=["Assembly"])
full_df.fillna(0, inplace=True)
full_df.drop_duplicates(inplace=True)

# Extract features and labels
X_full = full_df[[col for col in full_df.columns if col.startswith(('sero_', 'virus_'))]].values
y_full = full_df['label'].astype(int).values

imbalance = sum(y_full == 1) / sum(y_full == 0) if sum(y_full == 0) else 1

# Train the final model
final_model = XGBClassifier(
    scale_pos_weight=1 / imbalance,
    learning_rate=0.3,
    n_estimators=250,
    max_depth=7,
    eval_metric='logloss',
    use_label_encoder=False,
    tree_method="gpu_hist",
    predictor="gpu_predictor",
    device="cuda"
)

final_model.fit(X_full, y_full)

# Save the final model to disk
final_model_path = 'Model/model_full_data_xgb.pkl'
with open(final_model_path, 'wb') as f:
    pickle.dump(final_model, f)

print(f"Final model trained on all data and saved to '{final_model_path}'.")
