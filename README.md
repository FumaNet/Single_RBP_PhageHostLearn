# Single_RBP_PhageHostLearn

Repository containing the files to extend the PhageHostLearn pipeline to work with individual phage RBPs. 

PhageHostLearn original paper, "Prediction of Klebsiella phage-host specificity at the strain level" by Boeckaerts et al. https://pubmed.ncbi.nlm.nih.gov/38778023/
Associated Zenodo repository: https://zenodo.org/records/11061100 


## Data
The following files in the "Data" folder were downloaded from the abovementioned Zenodo repository:
- "Locibase.json"
- "esm2_embeddings_rbp.csv"
- "phage_host_interactions.csv"
- "RBPbase.csv"

The other files found in the "Data" folder were generated as shown in the "Pipeline_Extending_PHL.ipynb" notebook.

## Model
The "Model" folder contains an XGB Classifier trained on all available data as shown at the end of the "3_max_max_sero.py" file. The following hyperparameters were used: [scale_pos_weight=1 / imbalance, learning_rate=0.3, n_estimators=250, max_depth=7, eval_metric='logloss', use_label_encoder=False, tree_method="gpu_hist", predictor="gpu_predictor", device="cuda"]

## grouping
The "grouping" folder contains Klebsiella hosts grouped by genetic similarity at various thresholds, mimicking Boeckaerts et al.'s methodology, used for Leave-One-Group-Out (LOGO) cross-validation.

## Results
The "Results" folder contains the results of LOGO training algorithms at each similarity threshold, and a Jupyter Notebook used to generate the graphs in my paper from those results.

## Python Files
### 0_original_replica.py
Replicates PHL paper's methodology and results, having downloaded individual phage RBPs and host proteins, then averaging them for both phage and host.

### 1_max_max.py
Trains models on individual phage RBPs and host proteins, with all possible protein-protein combinations. Returns a surprisingly high ROC-AUC, but is shown to be significantly worse when evaluating PR curves.
 
### 2_max_max_original_sero.py
Introduces host grouped by serotype instead of keeping separate serotype-related proteins. Replicates PHL methodology on phages (averaging RBPs embeddings) and shows no drop in performance while significantly reducing the number of features, at the cost of not being generalizable to hosts with unidentified serotypes.

### 3_max_max_sero.py
Trains models matching individual phage RBPs to hot serotypes. Shows very promising performance, hinting at individual proteins' role in determining adsorption.






