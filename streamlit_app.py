import streamlit as st
import requests
import pandas as pd
import re
import os
import zipfile
import concurrent.futures

# ========= CONFIGURAÇÃO VISUAL ========= #
st.set_page_config(
    page_title="Shopify Image Exporter",
    page_icon="🛍️",
    layout="centered"
)

# CSS customizado (cores, botões e cards)
st.markdown("""
    <style>
        .main {
            background-color: #f9fafb;
            color: #1f2937;
            font-family: 'Inter', sans-serif;
        }
        h1, h2, h3 {
            color: #111827;
        }
        .stButton>button {
            background-color: #2563eb;
            color: white;
            border-radius: 8px;
            height: 3em;
            width: 100%;
            font-size: 16px;
        }
        .stButton>button:hover {
            background-color: #1d4ed8;
        }
        .stTextInput>div>div>input {
            border-radius: 6px;
            border: 1px solid #d1d5db;
        }
        .css-184tjsw p {
            color: #374151;
        }
    </style>
""", unsafe_allow_html=True)

# ========= CABEÇALHO ========= #
col1, col2 = st.columns([1, 4])
with col1:
    st.image("logo.png", width=90)
with col2:
    st.title("Shopify Image Exporter")
    st.caption("📸 Extraia rapidamente todas as imagens de produtos por coleção.")

st.markdown("---")

# ========= FUNÇÕES ========= #
def verificar_permissoes(base_url, headers):
    endpoints = {"Produtos": "/products.json?limit=1", "Coleções": "/custom_collections.json?limit=1"}
    resultados = {}
    for nome, endpoint in endpoints.items():
        r = requests.get(base_url + endpoint, headers=headers)
        resultados[nome] = r.status_code == 200
    return resultados

def buscar_colecoes(base_url, headers):
    colecoes = []
    for ctype in ["custom_collections", "smart_collections"]:
        url = f"{base_url}/{ctype}.json?limit=250"
        while True:
            r = requests.get(url, headers=headers)
            if r.status_code != 200:
                break
            for c in r.json().get(ctype, []):
                colecoes.append({
                    "id": str(c["id"]),
                    "handle": c.get("handle", ""),
                    "title": c.get("title", "")
                })
            if "link" in r.headers and "rel=\"next\"" in r.headers["link"]:
                page_info = r.headers["link"].split("page_info=")[-1].split(">")[0]
                url = f"{base_url}/{ctype}.json?limit=250&page_info={page_info}"
            else:
                break
    return colecoes

def buscar_produtos(base_url, headers, collection_id):
    produtos = []
    page_info = None
    while True:
        url = f"{base_url}/collections/{collection_id}/products.json?limit=250"
        if page_info:
            url += f"&page_info={page_info}"
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            break
        produtos.extend(r.json().get("products", []))
        if "link" in r.headers and "rel=\"next\"" in r.headers["link"]:
            page_info = r.headers["link"].split("page_info=")[-1].split(">")[0]
        else:
            break
    return produtos

def baixar_imagem(url, caminho):
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            with open(caminho, "wb") as f:
                f.write(response.content)
    except:
        pass

# ========= INTERFACE ========= #
st.subheader("🔧 Configuração de Acesso")
shop_name = st.text_input("Nome da Loja (ex: a608d7-cf)")
access_token = st.text_input("Access Token (shpat_...)", type="password")
collection_input = st.text_input("Coleção (ID, handle ou URL)")

modo = st.radio("Escolha o modo de exportação:", ["🔗 Apenas gerar CSV com links", "📦 Baixar imagens e gerar ZIP"])
turbo = False
if modo == "📦 Baixar imagens e gerar ZIP":
    turbo = st.checkbox("⚡ Ativar modo turbo (multithread)")

st.markdown("---")

if st.button("▶️ Iniciar Exportação"):
    if not shop_name or not access_token or not collection_input:
        st.warning("⚠️ Preencha todos os campos antes de continuar.")
    else:
        with st.spinner("Conectando à Shopify..."):
            api_version = "2023-10"
            base_url = f"https://{shop_name}.myshopify.com/admin/api/{api_version}"
            headers = {"X-Shopify-Access-Token": access_token}

            perms = verificar_permissoes(base_url, headers)
            if not all(perms.values()):
                st.error("Token sem permissões suficientes. Ative 'read_products' e 'read_collections'.")
                st.stop()

            colecoes = buscar_colecoes(base_url, headers)
            collection_id = None
            match = re.search(r'/collections/([^/?#]+)', collection_input)
            col_in = match.group(1) if match else collection_input.strip()

            for c in colecoes:
                if c["id"] == col_in or c["handle"].lower() == col_in.lower():
                    collection_id = c["id"]
                    nome_colecao = c["title"]
                    break

            if not collection_id:
                st.error("❌ Coleção não encontrada. Verifique o ID/handle e tente novamente.")
                st.stop()

            produtos = buscar_produtos(base_url, headers, collection_id)
            if not produtos:
                st.warning("Nenhum produto encontrado nesta coleção.")
                st.stop()

            st.success(f"✅ Coleção encontrada: **{nome_colecao}** — {len(produtos)} produtos")

            dados, tarefas = [], []
            os.makedirs("imagens_baixadas", exist_ok=True)

            for p in produtos:
                title = p.get("title", "")
                imagens = [img["src"] for img in p.get("images", [])]
                item = {"Título": title}
                for i, img in enumerate(imagens):
                    item[f"Imagem {i+1}"] = img
                    if modo == "📦 Baixar imagens e gerar ZIP":
                        pasta = os.path.join("imagens_baixadas", re.sub(r'[\\/*?:"<>|]', "_", title))
                        os.makedirs(pasta, exist_ok=True)
                        caminho = os.path.join(pasta, f"{i+1}.jpg")
                        tarefas.append((img, caminho))
                dados.append(item)

            if modo == "📦 Baixar imagens e gerar ZIP":
                st.info("Baixando imagens...")
                if turbo:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
                        list(executor.map(lambda x: baixar_imagem(*x), tarefas))
                else:
                    for t in tarefas:
                        baixar_imagem(*t)

                zip_name = f"imagens_colecao_{collection_id}.zip"
                with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for root, _, files in os.walk("imagens_baixadas"):
                        for file in files:
                            path = os.path.join(root, file)
                            zipf.write(path, os.path.relpath(path, "imagens_baixadas"))
                with open(zip_name, "rb") as f:
                    st.download_button("📥 Baixar ZIP", f, file_name=zip_name)

            df = pd.DataFrame(dados)
            csv_name = f"imagens_colecao_{collection_id}.csv"
            df.to_csv(csv_name, index=False, encoding="utf-8-sig")
            with open(csv_name, "rb") as f:
                st.download_button("📥 Baixar CSV", f, file_name=csv_name)

            st.success("🎉 Exportação concluída com sucesso!")
