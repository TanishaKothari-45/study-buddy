# Jupyter Notebooks for Study Buddy

This directory contains Jupyter notebooks for experimenting with different aspects of the RAG system.

## Available Notebooks

### 1. `chunking_strategies.ipynb`
**Purpose**: Experiment with different text chunking strategies for optimal RAG performance.

**Key Experiments**:
- Different chunk sizes (500, 1000, 1500, 2000 characters)
- Chunk overlap strategies (100, 200 characters)
- Context preservation analysis
- Information density measurement
- Real PDF processing examples

**Usage**:
```bash
cd notebooks
jupyter lab chunking_strategies.ipynb
```

### 2. `embeddings_evaluation.ipynb` (Coming Soon)
**Purpose**: Evaluate different embedding models and their performance.

**Planned Experiments**:
- Compare sentence-transformers models (all-MiniLM-L6-v2 vs others)
- Embedding dimension analysis
- Similarity metrics evaluation
- Performance benchmarks

### 3. `rag_evaluation.ipynb` (Coming Soon)
**Purpose**: Evaluate the complete RAG system performance.

**Planned Experiments**:
- Retrieval quality metrics (precision, recall, NDCG)
- Answer generation quality assessment
- End-to-end pipeline testing
- A/B testing of different configurations

## Setup Instructions

1. **Install Jupyter**:
   ```bash
   pip install jupyterlab
   ```

2. **Install notebook dependencies**:
   ```bash
   pip install pandas numpy matplotlib seaborn scikit-learn
   ```

3. **Run Jupyter Lab**:
   ```bash
   cd notebooks
   jupyter lab
   ```

## Running Experiments

Each notebook is designed to be self-contained and includes:
- Setup and imports
- Sample data generation
- Experiment execution
- Results analysis and visualization
- Conclusions and recommendations

## Best Practices

- **Start Small**: Begin with sample data before processing large PDFs
- **Iterate**: Use experiments to refine chunking and embedding strategies
- **Document**: Keep notes on what works best for different document types
- **Benchmark**: Always compare against baselines

## Data Sources

For realistic experiments, place sample PDFs in:
- `../data/pdfs/` - Raw PDF files
- `../data/processed/` - Will contain processed chunks and metadata

## Output

Experiment results and visualizations will help you:
- Choose optimal chunk sizes for your document types
- Select the best embedding models
- Fine-tune the RAG pipeline for UPSC content
- Understand performance characteristics
