from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import tempfile
import os
import numpy as np
import pandas as pd
import plotly.express as px
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_mistralai import ChatMistralAI
from langchain_mistralai.embeddings import MistralAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.prompts import ChatPromptTemplate

# Custom CSS for Premium Dashboard Theme
st.set_page_config(
    page_title="AI Medical Lab & Report Analyzer",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    /* Styling metric cards */
    .metric-card {
        background: rgba(128, 128, 128, 0.08);
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 12px;
        padding: 16px;
        text-align: center;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        margin-bottom: 16px;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 800;
        color: #4f46e5;
        margin-bottom: 2px;
    }
    .metric-label {
        font-size: 0.8rem;
        font-weight: 600;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    /* Section card container */
    .glass-card {
        background: rgba(128, 128, 128, 0.04);
        border: 1px solid rgba(128, 128, 128, 0.15);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 20px;
    }
    .glass-card h3 {
        margin-top: 0;
        color: #4f46e5;
        border-bottom: 1px solid rgba(128, 128, 128, 0.15);
        padding-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar - Settings & Configuration
st.sidebar.title("🔬 Lab Settings")
st.sidebar.markdown("Configure analysis and Machine Learning parameters:")

model_name = st.sidebar.selectbox(
    "Mistral LLM Model",
    ["mistral-large-latest", "mistral-small-latest"],
    index=0
)

temperature = st.sidebar.slider(
    "Model Temperature",
    min_value=0.0,
    max_value=1.0,
    value=0.3,
    step=0.1
)

k_chunks = st.sidebar.slider(
    "Retrieved Context Chunks (k)",
    min_value=1,
    max_value=10,
    value=5,
    step=1
)

n_clusters = st.sidebar.slider(
    "K-Means Topic Clusters",
    min_value=2,
    max_value=5,
    value=3,
    step=1
)

st.sidebar.markdown("---")
st.sidebar.info(
    "This system processes the document with an embedding model, clusters the semantic space using "
    "**K-Means**, projects the high-dimensional vectors to 2D using **PCA**, and uses **RAG** for analysis."
)

# Main Title and Description
st.title("🔬 AI Medical Lab & Report Analyzer")
st.markdown(
    "Upload a patient's medical PDF report to run advanced semantic analysis, extract key clinical findings, "
    "and visualize the document's semantic structure using unsupervised machine learning."
)

uploaded_file = st.file_uploader(
    "Upload Medical Report PDF",
    type=["pdf"]
)

# Verify API key is present
if not os.environ.get("MISTRAL_API_KEY"):
    st.error("⚠️ MISTRAL_API_KEY is not defined in the environment or `.env` file. Please set it to run the analysis.")

elif uploaded_file is not None:
    # Run analysis
    if st.button("Start Diagnostics & Semantic Mapping"):
        with st.spinner("Analyzing Report..."):
            
            # 1. Save uploaded file to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(uploaded_file.read())
                pdf_path = tmp_file.name

            try:
                # 2. Load PDF
                loader = PyPDFLoader(pdf_path)
                docs = loader.load()
                total_pages = len(docs)

                # 3. Split Documents
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=300,
                    chunk_overlap=50
                )
                split_docs = splitter.split_documents(docs)
                total_chunks = len(split_docs)

                # 4. Generate Embeddings & Run Unsupervised ML (PCA + K-means)
                embedding_model = MistralAIEmbeddings(model="mistral-embed")
                
                chunk_texts = [doc.page_content for doc in split_docs]
                
                # Retrieve embeddings
                embeddings = embedding_model.embed_documents(chunk_texts)
                X = np.array(embeddings)

                # 5. Chroma Vector store
                vectorstore = Chroma.from_documents(
                    documents=split_docs,
                    embedding=embedding_model,
                    persist_directory="./medical_chroma_db"
                )

                retriever = vectorstore.as_retriever(
                    search_type="similarity",
                    search_kwargs={"k": k_chunks}
                )

                query = """
                Analyze this medical report completely.
                Explain all important blood test values and possible health issues.
                Give diet suggestions and simplified explanations.
                """
                retrieved_docs = retriever.invoke(query)
                retrieved_texts = {doc.page_content for doc in retrieved_docs}
                
                # Check which chunks were retrieved
                is_retrieved = [doc.page_content in retrieved_texts for doc in split_docs]

                # Run PCA & Clustering if we have enough chunks
                ml_enabled = total_chunks >= 3
                if ml_enabled:
                    # K-Means clustering
                    actual_clusters = min(n_clusters, total_chunks)
                    kmeans = KMeans(n_clusters=actual_clusters, random_state=42, n_init='auto')
                    cluster_labels = kmeans.fit_predict(X)

                    # PCA
                    pca = PCA(n_components=2)
                    X_2d = pca.fit_transform(X)
                else:
                    cluster_labels = [0] * total_chunks
                    X_2d = np.zeros((total_chunks, 2))

                # Combine context
                context_text = "\n\n".join([doc.page_content for doc in retrieved_docs])

                # 6. LLM query
                llm = ChatMistralAI(
                    model=model_name,
                    temperature=temperature
                )

                prompt = ChatPromptTemplate.from_template("""
                You are an expert AI Medical Report Analyzer.

                Analyze the uploaded medical report carefully.

                Provide the response in the following format:

                1. Patient Health Summary
                2. Important Test Values
                3. Abnormal Values
                4. Possible Health Issues
                5. Diet Suggestions
                6. Lifestyle Recommendations
                7. Simplified Explanation for Normal People
                8. Emergency Warning Signs (if any)

                Rules:
                - Explain everything in simple language.
                - Mention normal ranges if available.
                - Be accurate and professional.
                - If values are normal, mention that clearly.
                - Do not create fake diseases.

                Very Important Disclaimer:
                "This AI analysis is not a replacement for professional doctors or medical advice."

                Medical Report Context:
                {context}

                Question:
                {question}
                """)

                final_prompt = prompt.format(
                    context=context_text,
                    question=query
                )

                response = llm.invoke(final_prompt)

                # Clean up PDF file
                os.remove(pdf_path)

                # 7. Render UI Components
                st.markdown("---")
                
                # Metrics Row
                m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                with m_col1:
                    st.markdown(f'<div class="metric-card"><div class="metric-value">{total_pages}</div><div class="metric-label">Pages Loaded</div></div>', unsafe_allow_html=True)
                with m_col2:
                    st.markdown(f'<div class="metric-card"><div class="metric-value">{total_chunks}</div><div class="metric-label">Text Chunks</div></div>', unsafe_allow_html=True)
                with m_col3:
                    st.markdown(f'<div class="metric-card"><div class="metric-value">{k_chunks}</div><div class="metric-label">Retrieved Chunks</div></div>', unsafe_allow_html=True)
                with m_col4:
                    st.markdown(f'<div class="metric-card"><div class="metric-value">{"Active" if ml_enabled else "Inactive"}</div><div class="metric-label">ML Clustering</div></div>', unsafe_allow_html=True)

                # Tabs
                tab1, tab2, tab3 = st.tabs([
                    "📋 Clinical Diagnostics", 
                    "🗺️ Semantic Document Map (PCA)", 
                    "🔍 Document Content Explorer"
                ])

                with tab1:
                    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                    st.write(response.content)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    st.error(
                        "Disclaimer: This AI analysis is not a replacement for professional doctors or medical advice."
                    )

                with tab2:
                    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                    st.subheader("Semantic Representation of Document")
                    st.markdown(
                        "Each dot represents a text chunk from the medical report. High-dimensional embeddings "
                        "generated by the deep learning model are clustered using **K-Means** (groups represent topics/themes) "
                        "and projected into 2D space using **PCA** (Principal Component Analysis)."
                    )
                    
                    if ml_enabled:
                        # Build DataFrame for Plotly
                        short_texts = [
                            text[:120] + "..." if len(text) > 120 else text 
                            for text in chunk_texts
                        ]
                        
                        df = pd.DataFrame({
                            "Component 1": X_2d[:, 0],
                            "Component 2": X_2d[:, 1],
                            "Cluster": [f"Topic {c+1}" for c in cluster_labels],
                            "Retrieved": ["Yes (Used in RAG)" if r else "No" for r in is_retrieved],
                            "Snippet": short_texts,
                            "Size": [18 if r else 8 for r in is_retrieved]
                        })

                        fig = px.scatter(
                            df,
                            x="Component 1",
                            y="Component 2",
                            color="Cluster",
                            symbol="Retrieved",
                            size="Size",
                            hover_data={"Snippet": True, "Component 1": False, "Component 2": False, "Size": False},
                            title="Interactive Document Chunk Space (Hover to inspect content)",
                            labels={"Component 1": "PCA Component 1", "Component 2": "PCA Component 2"},
                            color_discrete_sequence=px.colors.qualitative.Safe
                        )
                        
                        fig.update_layout(
                            legend_title_text="Clustering & RAG status",
                            plot_bgcolor="rgba(0,0,0,0)",
                            paper_bgcolor="rgba(0,0,0,0)",
                            margin=dict(l=10, r=10, t=40, b=10)
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("Not enough text chunks to perform clustering and dimensionality reduction (requires at least 3 chunks).")
                    st.markdown('</div>', unsafe_allow_html=True)

                with tab3:
                    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                    st.subheader("Explore Raw Chunk Contents")
                    st.markdown("Browse all the split segments of the uploaded PDF, color-coded by their K-means cluster assignment.")
                    
                    colors = ["#4f46e5", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"]
                    for idx, (doc, cluster) in enumerate(zip(split_docs, cluster_labels)):
                        c_color = colors[cluster % len(colors)]
                        is_ret = " [RETRIEVED]" if is_retrieved[idx] else ""
                        with st.expander(f"Chunk {idx+1} - Topic {cluster+1}{is_ret}"):
                            st.markdown(f"<span style='color:{c_color}; font-weight:bold;'>Topic Cluster {cluster+1}</span>", unsafe_allow_html=True)
                            st.write(doc.page_content)
                    st.markdown('</div>', unsafe_allow_html=True)

            except Exception as e:
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
                st.error(f"An error occurred during processing: {str(e)}")
