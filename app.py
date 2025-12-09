import pandas as pd
import numpy as np
import streamlit as st
import altair as alt
from datetime import datetime, date
import warnings
warnings.filterwarnings('ignore')

# ============================================
# CONFIGURAÇÃO
# ============================================
class Config:
    APP_TITLE = "📊 Dashboard Genérico - Arquitetura Medalhão"
    APP_LAYOUT = "wide"
    MAX_CATEGORY_VALUES = 20
    MAX_FILTERS = 3
    COLOR_PRIMARY = "#2196F3"
    COLOR_SECONDARY = "#4CAF50"
    COLOR_TERTIARY = "#FF5722"

def setup_page():
    st.set_page_config(
        page_title=Config.APP_TITLE,
        layout=Config.APP_LAYOUT,
        initial_sidebar_state="expanded",
        menu_items={
            'Get Help': 'https://github.com/seu-repo',
            'Report a bug': 'https://github.com/seu-repo/issues',
            'About': "Dashboard genérico para qualquer planilha - análise automática de dados"
        }
    )

# ============================================
# FUNÇÕES AUXILIARES
# ============================================

def format_date_for_display(date_value):
    """Formata data para exibição segura em qualquer componente"""
    if pd.isna(date_value) or date_value is None:
        return "N/A"
    
    try:
        if isinstance(date_value, (pd.Timestamp, datetime, date)):
            return date_value.strftime('%d/%m/%Y')
        elif isinstance(date_value, str):
            # Tenta converter string para data
            parsed = pd.to_datetime(date_value, errors='coerce')
            if pd.notnull(parsed):
                return parsed.strftime('%d/%m/%Y')
            return date_value[:20]  # Limita tamanho
        else:
            return str(date_value)[:20]
    except:
        return str(date_value)[:20]

def safe_numeric_value(value):
    """Converte qualquer valor para numérico de forma segura"""
    try:
        if pd.isna(value):
            return 0
        if isinstance(value, (int, float, np.number)):
            return float(value)
        # Tenta converter string para número
        clean_str = str(value).replace(',', '.').replace('R$', '').replace('$', '').strip()
        return float(clean_str)
    except:
        return 0

# ============================================
# CAMADA BRONZE (INGESTÃO)
# ============================================

@st.cache_data(ttl=3600, show_spinner="Carregando dados...")
def load_file(file) -> pd.DataFrame:
    """Carrega arquivo CSV ou Excel com tratamento robusto"""
    try:
        if file.name.lower().endswith('.csv'):
            # Tenta diferentes encodings
            encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
            for encoding in encodings:
                try:
                    file.seek(0)
                    df = pd.read_csv(file, encoding=encoding, low_memory=False)
                    if len(df) > 0:
                        st.sidebar.success(f"✅ Encoding: {encoding}")
                        return df
                except Exception as e:
                    continue
            
            # Fallback - leitura manual
            file.seek(0)
            df = pd.read_csv(file, encoding='utf-8', engine='python', on_bad_lines='skip')
            return df
        else:
            file.seek(0)
            # Tenta ler todas as sheets
            try:
                xls = pd.ExcelFile(file)
                if len(xls.sheet_names) > 1:
                    sheet_name = st.sidebar.selectbox("Selecione a planilha:", xls.sheet_names)
                    return pd.read_excel(file, sheet_name=sheet_name)
                return pd.read_excel(file)
            except:
                return pd.read_excel(file, engine='openpyxl')
    except Exception as e:
        st.error(f"❌ Erro ao carregar arquivo: {str(e)[:200]}")
        return pd.DataFrame()

def validate_dataframe(df: pd.DataFrame) -> dict:
    """Validação básica do DataFrame"""
    issues = []
    warnings = []
    
    if df.empty:
        issues.append("DataFrame vazio - arquivo não contém dados")
        return {"df": df, "issues": issues, "warnings": warnings}
    
    if len(df.columns) == 0:
        issues.append("Nenhuma coluna encontrada")
    
    # Renomeia colunas duplicadas
    duplicate_cols = df.columns[df.columns.duplicated()].tolist()
    if duplicate_cols:
        # Renomeia colunas duplicadas
        cols = {}
        counts = {}
        for col in df.columns:
            if col not in counts:
                counts[col] = 1
                cols[col] = col
            else:
                counts[col] += 1
                cols[col + f"_{counts[col]}"] = col
        
        df = df.rename(columns=cols)
        warnings.append(f"Colunas duplicadas renomeadas: {duplicate_cols}")
    
    # Remove colunas completamente vazias
    empty_cols = df.columns[df.isnull().all()].tolist()
    if empty_cols:
        df = df.drop(columns=empty_cols)
        warnings.append(f"Colunas vazias removidas: {empty_cols}")
    
    return {"df": df, "issues": issues, "warnings": warnings}

# ============================================
# CAMADA PRATA (TRANSFORMAÇÃO)
# ============================================

def detect_column_types(df: pd.DataFrame) -> dict:
    """Detecta tipos de colunas de forma robusta"""
    column_info = {}
    
    for col in df.columns:
        col_data = df[col].dropna()
        
        if len(col_data) == 0:
            column_info[col] = 'vazio'
            continue
        
        # Pega amostra para análise
        sample_size = min(100, len(col_data))
        sample = col_data.head(sample_size).astype(str).str.strip()
        
        # Testa se é numérico (prioridade)
        is_numeric = False
        numeric_count = 0
        
        for val in sample:
            try:
                # Remove caracteres não numéricos
                clean_val = str(val).replace(',', '.').replace('R$', '').replace('$', '').strip()
                float(clean_val)
                numeric_count += 1
            except:
                pass
        
        if numeric_count / sample_size > 0.7:  # Mais de 70% dos valores são numéricos
            column_info[col] = 'numerico'
            continue
        
        # Testa se é data
        is_date = False
        date_patterns = [
            r'\d{4}[-/]\d{2}[-/]\d{2}',  # YYYY-MM-DD ou YYYY/MM/DD
            r'\d{2}[-/]\d{2}[-/]\d{4}',  # DD-MM-YYYY ou DD/MM/YYYY
            r'\d{2}[-/]\d{2}[-/]\d{2}',  # DD-MM-YY ou DD/MM/YY
        ]
        
        for pattern in date_patterns:
            if sample.str.contains(pattern, regex=True).any():
                is_date = True
                break
        
        if is_date:
            # Verifica se pode ser convertido para datetime
            try:
                pd.to_datetime(col_data.head(10), errors='raise')
                column_info[col] = 'data'
            except:
                column_info[col] = 'texto'
            continue
        
        # Testa categórico
        unique_vals = col_data.nunique()
        total_vals = len(col_data)
        
        if unique_vals < 50 and unique_vals / total_vals < 0.5:
            column_info[col] = 'categoria'
        else:
            column_info[col] = 'texto'
    
    return column_info

def clean_data(df: pd.DataFrame, column_types: dict) -> pd.DataFrame:
    """Limpeza básica dos dados com conversões seguras"""
    df_clean = df.copy()
    
    for col in df_clean.columns:
        col_type = column_types.get(col, 'texto')
        
        # Limpa strings básicas
        if col_type in ['categoria', 'texto']:
            df_clean[col] = df_clean[col].astype(str).str.strip()
            df_clean[col] = df_clean[col].replace(['nan', 'None', 'NaN', 'null', 'NULL', ''], pd.NA)
        
        # Converte datas
        elif col_type == 'data':
            try:
                df_clean[col] = pd.to_datetime(df_clean[col], errors='coerce', dayfirst=True)
            except:
                df_clean[col] = pd.NA
        
        # Converte numéricos
        elif col_type == 'numerico':
            df_clean[col] = df_clean[col].apply(safe_numeric_value)
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
    
    # Remove duplicatas exatas
    initial_rows = len(df_clean)
    df_clean = df_clean.drop_duplicates()
    removed_duplicates = initial_rows - len(df_clean)
    
    if removed_duplicates > 0:
        st.sidebar.info(f"🔄 {removed_duplicates} duplicatas removidas")
    
    return df_clean

# ============================================
# CAMADA OURO (ANÁLISE)
# ============================================

def calculate_basic_metrics(df: pd.DataFrame, column_types: dict) -> dict:
    """Calcula métricas básicas de forma segura"""
    metrics = {
        'total_registros': len(df),
        'total_colunas': len(df.columns),
        'registros_unicos': len(df.drop_duplicates()),
        'nulos_totais': df.isnull().sum().sum(),
        'percentual_nulos': 0,
        'colunas_numericas': 0,
        'colunas_categoricas': 0,
        'colunas_data': 0,
        'colunas_texto': 0
    }
    
    if len(df) > 0:
        metrics['percentual_nulos'] = (df.isnull().sum().sum() / (len(df) * len(df.columns))) * 100
    
    # Conta tipos de colunas
    for tipo in column_types.values():
        if tipo == 'numerico':
            metrics['colunas_numericas'] += 1
        elif tipo == 'categoria':
            metrics['colunas_categoricas'] += 1
        elif tipo == 'data':
            metrics['colunas_data'] += 1
        elif tipo == 'texto':
            metrics['colunas_texto'] += 1
    
    # Calcula média se houver colunas numéricas
    numeric_cols = [col for col, tipo in column_types.items() if tipo == 'numerico']
    if numeric_cols:
        try:
            metrics['media_geral'] = df[numeric_cols].mean().mean()
        except:
            metrics['media_geral'] = 0
    
    return metrics

# ============================================
# FUNÇÕES DE VISUALIZAÇÃO SEGURAS
# ============================================

def create_bar_chart(df: pd.DataFrame, column: str, title: str, color: str, limit: int = 10):
    """Cria gráfico de barras simples com tratamento de erros"""
    if column not in df.columns:
        return None
    
    try:
        # Conta valores não nulos
        non_null_data = df[column].dropna()
        if len(non_null_data) == 0:
            return None
        
        # Limita valores únicos para performance
        value_counts = non_null_data.value_counts().head(limit).reset_index()
        value_counts.columns = ['Categoria', 'Quantidade']
        
        # Converte categorias para string
        value_counts['Categoria'] = value_counts['Categoria'].astype(str)
        
        # Ordena por quantidade
        value_counts = value_counts.sort_values('Quantidade', ascending=True)
        
        chart = alt.Chart(value_counts).mark_bar(color=color).encode(
            y=alt.Y('Categoria:N', sort=None, title=column),
            x=alt.X('Quantidade:Q', title='Quantidade'),
            tooltip=['Categoria', 'Quantidade']
        ).properties(
            title=title[:50],  # Limita título
            height=300
        )
        
        return chart
    except Exception as e:
        st.sidebar.warning(f"Não foi possível criar gráfico para {column}: {str(e)[:50]}")
        return None

def create_pie_chart(df: pd.DataFrame, column: str, title: str, colors: list = None):
    """Cria gráfico de pizza/donut seguro"""
    if column not in df.columns:
        return None
    
    try:
        # Conta valores
        value_counts = df[column].dropna().value_counts().head(8).reset_index()
        value_counts.columns = ['Categoria', 'Quantidade']
        
        if len(value_counts) == 0:
            return None
        
        # Converte para string
        value_counts['Categoria'] = value_counts['Categoria'].astype(str)
        
        # Usa cores padrão se não fornecidas
        if not colors:
            colors = ['#4CAF50', '#2196F3', '#FF9800', '#9C27B0', '#F44336', '#00BCD4']
        
        color_scale = alt.Scale(
            domain=value_counts['Categoria'].tolist(),
            range=colors[:len(value_counts)]
        )
        
        chart = alt.Chart(value_counts).mark_arc(innerRadius=50).encode(
            theta=alt.Theta('Quantidade:Q'),
            color=alt.Color('Categoria:N', scale=color_scale),
            tooltip=['Categoria', 'Quantidade']
        ).properties(
            title=title[:50],
            height=300,
            width=300
        )
        
        return chart
    except:
        return None

def create_histogram(df: pd.DataFrame, column: str, title: str, color: str, bins: int = 20):
    """Cria histograma simples"""
    if column not in df.columns:
        return None
    
    try:
        # Remove nulos
        data = df[column].dropna()
        if len(data) == 0:
            return None
        
        chart = alt.Chart(df).mark_bar(color=color).encode(
            alt.X(f'{column}:Q', bin=alt.Bin(maxbins=bins), title=column),
            alt.Y('count()', title='Frequência'),
            tooltip=['count()']
        ).properties(
            title=title[:50],
            height=300
        )
        
        return chart
    except:
        return None

def create_scatter_plot(df: pd.DataFrame, x_col: str, y_col: str, title: str, color: str):
    """Cria gráfico de dispersão simples"""
    if x_col not in df.columns or y_col not in df.columns:
        return None
    
    try:
        # Remove nulos para ambos os eixos
        clean_df = df[[x_col, y_col]].dropna()
        if len(clean_df) == 0:
            return None
        
        chart = alt.Chart(clean_df).mark_circle(size=60).encode(
            x=alt.X(f'{x_col}:Q', title=x_col),
            y=alt.Y(f'{y_col}:Q', title=y_col),
            color=alt.value(color),
            tooltip=[x_col, y_col]
        ).properties(
            title=title[:50],
            height=300
        )
        
        return chart
    except:
        return None

def create_date_line_chart(df: pd.DataFrame, date_col: str, title: str, color: str):
    """Cria gráfico de linha para datas"""
    if date_col not in df.columns:
        return None
    
    try:
        # Cria cópia para não modificar original
        df_temp = df.copy()
        
        # Remove datas nulas
        df_temp = df_temp.dropna(subset=[date_col])
        if len(df_temp) == 0:
            return None
        
        # Conta por data
        df_temp['_date_day'] = df_temp[date_col].dt.date
        contagem_diaria = df_temp.groupby('_date_day').size().reset_index()
        contagem_diaria.columns = ['Data', 'Contagem']
        contagem_diaria = contagem_diaria.sort_values('Data')
        
        if len(contagem_diaria) < 2:
            return None
        
        # Gráfico de linha
        chart = alt.Chart(contagem_diaria).mark_line(point=True, color=color).encode(
            x=alt.X('Data:T', title='Data'),
            y=alt.Y('Contagem:Q', title='Contagem'),
            tooltip=['Data', 'Contagem']
        ).properties(
            title=title[:50],
            height=300
        )
        
        return chart
    except Exception as e:
        st.sidebar.warning(f"Erro no gráfico de data {date_col}: {str(e)[:50]}")
        return None

def create_table_summary(df: pd.DataFrame, column_types: dict) -> pd.DataFrame:
    """Cria tabela resumo das colunas de forma segura"""
    summary = []
    
    for col in df.columns:
        col_type = column_types.get(col, 'desconhecido')
        n_nulls = df[col].isnull().sum()
        total = len(df)
        pct_nulls = (n_nulls / total * 100) if total > 0 else 0
        unique_values = df[col].nunique()
        
        if col_type == 'numerico':
            try:
                stats = df[col].describe()
                info = f"Média: {stats.get('mean', 0):.2f}, Mediana: {stats.get('50%', 0):.2f}"
            except:
                info = "Dados numéricos"
        elif col_type == 'categoria':
            try:
                top_value = df[col].mode().iloc[0] if len(df[col].mode()) > 0 else "N/A"
                info = f"Mais comum: {str(top_value)[:30]}"
            except:
                info = "Dados categóricos"
        elif col_type == 'data':
            try:
                min_date = df[col].min()
                max_date = df[col].max()
                min_str = format_date_for_display(min_date)
                max_str = format_date_for_display(max_date)
                info = f"De {min_str} a {max_str}"
            except:
                info = "Dados de data"
        else:
            info = "Texto ou outro"
        
        summary.append({
            'Coluna': col,
            'Tipo': col_type,
            'Nulos': f"{n_nulls} ({pct_nulls:.1f}%)",
            'Valores Únicos': unique_values,
            'Informações': info
        })
    
    return pd.DataFrame(summary)

# ============================================
# INTERFACE PRINCIPAL
# ============================================

def main():
    # Configuração
    setup_page()
    
    # Título
    st.title("📊 Dashboard Genérico - Visualizações Simples")
    st.markdown("---")
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Configurações")
        st.markdown("---")
        
        # Upload do arquivo
        uploaded_file = st.file_uploader(
            "📁 Envie seu arquivo (CSV ou Excel)",
            type=['csv', 'xlsx', 'xls'],
            help="Suporta CSV e Excel. Até 200MB."
        )
        
        st.markdown("---")
        
        # Informações sobre arquitetura
        st.header("🏗️ Arquitetura Medalhão")
        with st.expander("ℹ️ Como funciona", expanded=False):
            st.markdown("""
            **Bronze** 🟠  
            - Upload do arquivo  
            - Validação básica  
            - Detecção automática de tipos
            
            **Prata** ⚪  
            - Limpeza dos dados  
            - Conversões seguras  
            - Tratamento de erros
            
            **Ouro** 🟡  
            - Análise automática  
            - Gráficos adaptáveis  
            - Relatórios dinâmicos
            """)
        
        # Configurações de cores
        st.markdown("---")
        st.header("🎨 Cores dos Gráficos")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            cor_primaria = st.color_picker("Primária", Config.COLOR_PRIMARY, key="primaria")
        with col2:
            cor_secundaria = st.color_picker("Secundária", Config.COLOR_SECONDARY, key="secundaria")
        with col3:
            cor_terciaria = st.color_picker("Terciária", Config.COLOR_TERTIARY, key="terciaria")
        
        # Cores para pizza
        st.markdown("**Cores para gráficos de pizza:**")
        pizza_cols = st.columns(6)
        cores_pizza = []
        color_defaults = ["#4CAF50", "#2196F3", "#FF9800", "#9C27B0", "#F44336", "#00BCD4"]
        
        for i in range(6):
            with pizza_cols[i]:
                cor = st.color_picker(f"C{i+1}", color_defaults[i], key=f"pizza_{i}")
                cores_pizza.append(cor)
        
        st.markdown("---")
        
        # Configurações avançadas
        with st.expander("⚙️ Configurações Avançadas", expanded=False):
            max_categories = st.slider("Máx. categorias por gráfico", 5, 50, 10)
            show_all_cols = st.checkbox("Mostrar todas colunas em gráficos", value=False)
        
        st.markdown("---")
        
        # Botão reset
        if st.button("🔄 Resetar Dashboard", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    
    # Se não houver arquivo, mostra instruções
    if uploaded_file is None:
        col1, col2, col3 = st.columns([1, 3, 1])
        
        with col2:
            st.info("👈 Use a barra lateral para fazer upload de um arquivo")
            
            st.markdown("### 🎯 Recursos do Dashboard")
            
            st.markdown("""
            - 📊 **Gráficos automáticos** - detecta tipos de dados automaticamente
            - 📋 **Análise completa** - métricas, distribuições, tendências
            - 🔍 **Filtros dinâmicos** - filtre por qualquer coluna categórica
            - 🎨 **Cores personalizáveis** - personalize todas as cores
            - 📈 **Visualizações inteligentes** - gráficos adequados para cada tipo de dado
            - 💾 **Download** - baixe dados processados e relatórios
            - 🛡️ **Robusto** - lida com erros e dados incompletos
            """)
            
            # Exemplo de dados
            st.markdown("### 📝 Funciona com qualquer planilha")
            
            exemplo = pd.DataFrame({
                'Data': ['2025-10-06', '2025-10-07', '2025-10-08', '2025-10-09'],
                'Categoria': ['A', 'B', 'A', 'C'],
                'Valor': [150.50, 230.00, 189.99, 310.25],
                'Quantidade': [10, 15, 8, 12],
                'Status': ['Ativo', 'Inativo', 'Ativo', 'Pendente']
            })
            
            st.dataframe(exemplo, use_container_width=True)
            
            st.markdown("""
            **O dashboard irá automaticamente:**
            1. 🔍 Detectar tipos de dados (data, número, categoria, texto)
            2. 📊 Criar gráficos apropriados para cada tipo
            3. 📈 Calcular estatísticas relevantes
            4. 🎨 Aplicar cores personalizadas
            5. 📋 Gerar relatório completo
            """)
        
        return
    
    # ============================================
    # PROCESSAMENTO DOS DADOS
    # ============================================
    
    # BRONZE: Carregamento
    with st.spinner("🟠 Carregando dados..."):
        df_raw = load_file(uploaded_file)
        validation = validate_dataframe(df_raw)
        
        if validation["issues"]:
            for issue in validation["issues"]:
                st.error(f"❌ {issue}")
            if st.button("🔄 Tentar novamente"):
                st.rerun()
            return
        
        if validation["warnings"]:
            for warning in validation["warnings"]:
                st.warning(f"⚠️ {warning}")
    
    # PRATA: Limpeza e transformação
    with st.spinner("⚪ Processando dados..."):
        column_types = detect_column_types(df_raw)
        df_clean = clean_data(df_raw, column_types)
    
    # Mostrar status na sidebar
    st.sidebar.success(f"✅ {uploaded_file.name[:30]}")
    st.sidebar.metric("📊 Registros", f"{len(df_clean):,}")
    st.sidebar.metric("📋 Colunas", len(df_clean.columns))
    
    # ============================================
    # FILTROS DINÂMICOS
    # ============================================
    
    st.sidebar.markdown("---")
    st.sidebar.header("🔍 Filtros")
    
    filters = {}
    categoria_cols = [col for col, tipo in column_types.items() if tipo == 'categoria']
    
    if categoria_cols:
        for col in categoria_cols[:Config.MAX_FILTERS]:
            unique_vals = df_clean[col].dropna().unique()
            if len(unique_vals) > 0:
                unique_vals = ['Todos'] + sorted([str(v) for v in unique_vals])
                selected = st.sidebar.selectbox(col, unique_vals, key=f"filter_{col}")
                
                if selected != 'Todos':
                    filters[col] = selected
    
    # Aplicar filtros
    df_filtered = df_clean.copy()
    if filters:
        for col, value in filters.items():
            if value != 'Todos':
                df_filtered = df_filtered[df_filtered[col].astype(str) == value]
    
    # Mostrar filtros ativos
    if filters:
        st.sidebar.markdown("---")
        st.sidebar.header("📋 Filtros Ativos")
        for col, val in filters.items():
            if val != 'Todos':
                st.sidebar.info(f"**{col}:** {val}")
        st.sidebar.metric("📈 Registros Filtrados", len(df_filtered))
    
    # ============================================
    # ANÁLISE E VISUALIZAÇÃO
    # ============================================
    
    # Abas principais
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Visão Geral", 
        "📈 Gráficos", 
        "📋 Dados", 
        "🔍 Qualidade"
    ])
    
    # ============================================
    # ABA 1: VISÃO GERAL (MÉTRICAS)
    # ============================================
    with tab1:
        st.header("📈 Métricas Principais")
        
        # Métricas básicas
        metrics = calculate_basic_metrics(df_filtered, column_types)
        
        # Primeira linha
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total de Registros", f"{metrics['total_registros']:,}")
        
        with col2:
            st.metric("Total de Colunas", metrics['total_colunas'])
        
        with col3:
            st.metric("Registros Únicos", f"{metrics['registros_unicos']:,}")
        
        with col4:
            st.metric("Valores Nulos", f"{metrics['nulos_totais']:,}")
        
        # Segunda linha
        col5, col6, col7, col8 = st.columns(4)
        
        with col5:
            st.metric("% Nulos", f"{metrics['percentual_nulos']:.1f}%")
        
        with col6:
            st.metric("Colunas Numéricas", metrics['colunas_numericas'])
        
        with col7:
            if 'media_geral' in metrics and metrics['media_geral'] != 0:
                st.metric("Média Geral", f"{metrics['media_geral']:.2f}")
            else:
                st.metric("Média Geral", "N/A")
        
        with col8:
            st.metric("Colunas Categóricas", metrics['colunas_categoricas'])
        
        # Terceira linha
        col9, col10, col11, col12 = st.columns(4)
        
        with col9:
            st.metric("Colunas de Data", metrics['colunas_data'])
        
        with col10:
            st.metric("Colunas de Texto", metrics['colunas_texto'])
        
        with col11:
            duplicatas = len(df_clean) - metrics['registros_unicos']
            st.metric("Duplicatas Removidas", duplicatas)
        
        with col12:
            completeness = 100 - metrics['percentual_nulos']
            st.metric("Completude", f"{completeness:.1f}%")
        
        st.markdown("---")
        
        # Tipos de dados encontrados
        st.header("📋 Tipos de Dados Detectados")
        
        type_counts = {
            'Numérico': metrics['colunas_numericas'],
            'Categórico': metrics['colunas_categoricas'],
            'Data': metrics['colunas_data'],
            'Texto': metrics['colunas_texto']
        }
        
        # Remove tipos com zero
        type_counts = {k: v for k, v in type_counts.items() if v > 0}
        
        if type_counts:
            # Gráfico de pizza dos tipos
            type_df = pd.DataFrame({
                'Tipo': list(type_counts.keys()),
                'Quantidade': list(type_counts.values())
            })
            
            chart = alt.Chart(type_df).mark_arc(innerRadius=50).encode(
                theta='Quantidade:Q',
                color=alt.Color('Tipo:N', scale=alt.Scale(
                    domain=type_df['Tipo'].tolist(),
                    range=cores_pizza[:len(type_df)]
                )),
                tooltip=['Tipo', 'Quantidade']
            ).properties(
                height=300,
                title="Distribuição por Tipo de Dado"
            )
            
            st.altair_chart(chart, use_container_width=True)
        
        # Tabela de tipos
        st.subheader("📝 Detalhes por Coluna")
        tipo_df = pd.DataFrame([
            {"Coluna": col, "Tipo": tipo} 
            for col, tipo in column_types.items()
        ])
        
        st.dataframe(tipo_df, use_container_width=True, height=200)
    
    # ============================================
    # ABA 2: GRÁFICOS
    # ============================================
    with tab2:
        st.header("📈 Análise por Tipo de Dado")
        
        # Mostrar cores ativas
        with st.expander("🎨 Cores Ativas", expanded=False):
            col_c1, col_c2, col_c3 = st.columns(3)
            with col_c1:
                st.color_picker("Primária", cor_primaria, disabled=True)
            with col_c2:
                st.color_picker("Secundária", cor_secundaria, disabled=True)
            with col_c3:
                st.color_picker("Terciária", cor_terciaria, disabled=True)
        
        # ============================================
        # SEÇÃO 1: COLUNAS CATEGÓRICAS
        # ============================================
        categoria_cols = [col for col, tipo in column_types.items() if tipo == 'categoria']
        
        if categoria_cols:
            st.subheader("🏷️ Análise de Categorias")
            
            # Mostrar até 2 gráficos por linha
            cols_per_row = 2
            for i in range(0, len(categoria_cols), cols_per_row):
                cols = st.columns(cols_per_row)
                
                for j, col_name in enumerate(categoria_cols[i:i+cols_per_row]):
                    with cols[j]:
                        # Gráfico de barras
                        chart = create_bar_chart(
                            df_filtered, 
                            col_name, 
                            f"Top {max_categories} - {col_name}",
                            cor_primaria if j % 2 == 0 else cor_secundaria,
                            limit=max_categories
                        )
                        
                        if chart:
                            st.altair_chart(chart, use_container_width=True)
                        
                        # Estatísticas rápidas
                        value_counts = df_filtered[col_name].dropna().value_counts()
                        if len(value_counts) > 0:
                            st.caption(f"**Valores únicos:** {len(value_counts)}")
                            st.caption(f"**Valor mais comum:** {str(value_counts.index[0])[:30]}")
            
            st.markdown("---")
            
            # Gráfico de pizza para a primeira categoria
            if len(categoria_cols) > 0:
                st.subheader("🍕 Distribuição em Pizza")
                
                col_p1, col_p2 = st.columns([2, 1])
                
                with col_p1:
                    primeira_categoria = categoria_cols[0]
                    pizza_chart = create_pie_chart(
                        df_filtered,
                        primeira_categoria,
                        f"Distribuição - {primeira_categoria}",
                        cores_pizza
                    )
                    
                    if pizza_chart:
                        st.altair_chart(pizza_chart, use_container_width=True)
                
                with col_p2:
                    st.markdown("**Estatísticas:**")
                    value_counts = df_filtered[primeira_categoria].value_counts().head(5)
                    for valor, quantidade in value_counts.items():
                        st.metric(str(valor)[:20], quantidade)
        
        # ============================================
        # SEÇÃO 2: COLUNAS NUMÉRICAS
        # ============================================
        numerico_cols = [col for col, tipo in column_types.items() if tipo == 'numerico']
        
        if numerico_cols:
            st.subheader("🔢 Análise Numérica")
            
            # Primeira linha: histogramas
            cols_per_row = 2
            for i in range(0, min(4, len(numerico_cols)), cols_per_row):
                cols = st.columns(cols_per_row)
                
                for j, col_name in enumerate(numerico_cols[i:i+cols_per_row]):
                    with cols[j]:
                        # Histograma
                        chart = create_histogram(
                            df_filtered,
                            col_name,
                            f"Distribuição - {col_name}",
                            cor_terciaria if j % 2 == 0 else cor_primaria,
                            bins=15
                        )
                        
                        if chart:
                            st.altair_chart(chart, use_container_width=True)
                        
                        # Estatísticas
                        try:
                            stats = df_filtered[col_name].describe()
                            col_stat1, col_stat2, col_stat3 = st.columns(3)
                            with col_stat1:
                                st.metric("Média", f"{stats.get('mean', 0):.2f}")
                            with col_stat2:
                                st.metric("Mediana", f"{stats.get('50%', 0):.2f}")
                            with col_stat3:
                                st.metric("Desvio", f"{stats.get('std', 0):.2f}")
                        except:
                            pass
            
            st.markdown("---")
            
            # Segunda linha: dispersão se houver pelo menos 2 colunas numéricas
            if len(numerico_cols) >= 2:
                st.subheader("📊 Relação entre Variáveis")
                
                col_sc1, col_sc2 = st.columns(2)
                
                with col_sc1:
                    # Seleção de eixos
                    x_axis = st.selectbox(
                        "Eixo X",
                        numerico_cols,
                        key="scatter_x"
                    )
                
                with col_sc2:
                    y_options = [col for col in numerico_cols if col != x_axis]
                    if y_options:
                        y_axis = st.selectbox(
                            "Eixo Y",
                            y_options,
                            index=0,
                            key="scatter_y"
                        )
                    else:
                        y_axis = None
                
                # Gráfico de dispersão
                if x_axis and y_axis:
                    scatter_chart = create_scatter_plot(
                        df_filtered,
                        x_axis,
                        y_axis,
                        f"{y_axis} vs {x_axis}",
                        cor_secundaria
                    )
                    
                    if scatter_chart:
                        st.altair_chart(scatter_chart, use_container_width=True)
                    
                    # Correlação simples
                    try:
                        correlacao = df_filtered[x_axis].corr(df_filtered[y_axis])
                        st.info(f"**Correlação:** {correlacao:.3f}")
                        
                        if correlacao > 0.7:
                            st.success("Forte correlação positiva")
                        elif correlacao < -0.7:
                            st.success("Forte correlação negativa")
                        elif abs(correlacao) < 0.3:
                            st.info("Correlação fraca")
                    except:
                        pass
        
        # ============================================
        # SEÇÃO 3: DATAS (CORRIGIDA)
        # ============================================
        data_cols = [col for col, tipo in column_types.items() if tipo == 'data']
        
        if data_cols:
            st.subheader("📅 Análise de Datas")
            
            for col_name in data_cols[:2]:  # Máximo 2 gráficos de data
                # Gráfico de linha para datas
                chart = create_date_line_chart(
                    df_filtered,
                    col_name,
                    f"Contagem por Data - {col_name}",
                    cor_primaria
                )
                
                if chart:
                    st.altair_chart(chart, use_container_width=True)
                
                # Estatísticas SEGURAS
                try:
                    # Remove nulos
                    dates = df_filtered[col_name].dropna()
                    
                    if len(dates) > 0:
                        col_d1, col_d2, col_d3 = st.columns(3)
                        
                        with col_d1:
                            primeira_data = dates.min()
                            st.metric("Primeira Data", format_date_for_display(primeira_data))
                        
                        with col_d2:
                            ultima_data = dates.max()
                            st.metric("Última Data", format_date_for_display(ultima_data))
                        
                        with col_d3:
                            dias_total = (ultima_data - primeira_data).days if hasattr(ultima_data, '__sub__') else 0
                            st.metric("Total de Dias", dias_total)
                except Exception as e:
                    st.warning(f"Não foi possível calcular estatísticas para {col_name}")
        
        # ============================================
        # MENSAGEM SE NÃO HOUVER DADOS PARA ANÁLISE
        # ============================================
        if not categoria_cols and not numerico_cols and not data_cols:
            st.warning("⚠️ Nenhuma coluna adequada para análise gráfica foi encontrada.")
            st.info("""
            **Sugestões:**
            1. Verifique se seu arquivo tem colunas numéricas, de data ou categóricas
            2. Colunas de texto puro não são analisadas graficamente
            3. O dashboard ainda mostrará os dados brutos na aba "Dados"
            """)
    
    # ============================================
    # ABA 3: DADOS
    # ============================================
    with tab3:
        st.header("📋 Visualização dos Dados")
        
        # Controles
        col_cont1, col_cont2, col_cont3 = st.columns(3)
        
        with col_cont1:
            buscar = st.text_input("🔍 Buscar em todas as colunas", placeholder="Digite para filtrar...")
        
        with col_cont2:
            linhas_mostrar = st.slider("Linhas por página", 10, 100, 30, key="linhas_por_pagina")
        
        with col_cont3:
            mostrar_todas_cols = st.checkbox("Mostrar todas as colunas", value=False)
        
        # Aplicar busca
        df_display = df_filtered.copy()
        if buscar:
            try:
                # Busca case-insensitive em todas as colunas
                mask = df_display.astype(str).apply(
                    lambda x: x.str.contains(buscar, case=False, na=False)
                ).any(axis=1)
                df_display = df_display[mask]
                st.success(f"Encontrados {len(df_display)} registros com '{buscar}'")
            except:
                st.warning("Não foi possível aplicar a busca")
        
        # Selecionar colunas para mostrar
        if not mostrar_todas_cols and len(df_display.columns) > 8:
            colunas_selecionadas = st.multiselect(
                "Selecione colunas para mostrar:",
                df_display.columns.tolist(),
                default=df_display.columns.tolist()[:6]
            )
            
            if colunas_selecionadas:
                df_display = df_display[colunas_selecionadas]
        
        # Formatar datas para exibição
        df_display_formatted = df_display.copy()
        for col in data_cols:
            if col in df_display_formatted.columns:
                df_display_formatted[col] = df_display_formatted[col].apply(format_date_for_display)
        
        # Mostrar dados
        st.dataframe(
            df_display_formatted.head(linhas_mostrar),
            use_container_width=True,
            height=400
        )
        
        st.info(f"Mostrando {min(linhas_mostrar, len(df_display))} de {len(df_display):,} registros")
        
        # Download
        st.markdown("---")
        st.subheader("💾 Download dos Dados")
        
        col_dl1, col_dl2, col_dl3 = st.columns(3)
        
        with col_dl1:
            csv = df_filtered.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Baixar CSV Filtrado",
                data=csv,
                file_name=f"dados_filtrados_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col_dl2:
            # Resumo em CSV
            resumo = create_table_summary(df_clean, column_types)
            resumo_csv = resumo.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📊 Baixar Resumo",
                data=resumo_csv,
                file_name=f"resumo_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col_dl3:
            # Dados brutos originais
            csv_raw = df_raw.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📄 Baixar Dados Originais",
                data=csv_raw,
                file_name=f"dados_originais_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True
            )
    
    # ============================================
    # ABA 4: QUALIDADE
    # ============================================
    with tab4:
        st.header("🔍 Análise de Qualidade")
        
        # Tabela de resumo
        st.subheader("📋 Resumo por Coluna")
        
        resumo_df = create_table_summary(df_clean, column_types)
        st.dataframe(resumo_df, use_container_width=True, height=400)
        
        st.markdown("---")
        
        # Análise de nulos
        st.subheader("📊 Valores Nulos por Coluna")
        
        nulos_por_coluna = df_clean.isnull().sum()
        nulos_por_coluna = nulos_por_coluna[nulos_por_coluna > 0].sort_values(ascending=False)
        
        if len(nulos_por_coluna) > 0:
            # Converter para DataFrame para gráfico
            nulos_df = pd.DataFrame({
                'Coluna': nulos_por_coluna.index,
                'Nulos': nulos_por_coluna.values
            })
            nulos_df['Percentual'] = (nulos_df['Nulos'] / len(df_clean)) * 100
            
            # Gráfico de barras
            chart = alt.Chart(nulos_df).mark_bar(color="#F44336").encode(
                x=alt.X('Percentual:Q', title='Percentual de Nulos (%)'),
                y=alt.Y('Coluna:N', sort='-x', title='Coluna'),
                tooltip=['Coluna', 'Nulos', 'Percentual']
            ).properties(
                height=min(400, len(nulos_df) * 30),
                title="Colunas com Valores Nulos"
            )
            
            st.altair_chart(chart, use_container_width=True)
            
            # Recomendações
            st.warning("⚠️ Recomendações:")
            
            for _, row in nulos_df.iterrows():
                pct = row['Percentual']
                if pct > 50:
                    st.error(f"- **{row['Coluna']}**: {pct:.1f}% nulos → Considere remover esta coluna")
                elif pct > 20:
                    st.warning(f"- **{row['Coluna']}**: {pct:.1f}% nulos → Muitos valores faltantes")
                elif pct > 5:
                    st.info(f"- **{row['Coluna']}**: {pct:.1f}% nulos → Alguns valores faltantes")
        else:
            st.success("✅ Nenhum valor nulo encontrado!")
        
        st.markdown("---")
        
        # Outras métricas de qualidade
        st.subheader("📈 Outras Métricas de Qualidade")
        
        col_q1, col_q2, col_q3, col_q4 = st.columns(4)
        
        with col_q1:
            duplicatas = len(df_clean) - len(df_clean.drop_duplicates())
            st.metric("Registros Duplicados", duplicatas)
        
        with col_q2:
            colunas_problematicas = len([col for col in df_clean.columns 
                                        if df_clean[col].isnull().sum() / len(df_clean) > 0.3])
            st.metric("Colunas Problemáticas", colunas_problematicas)
        
        with col_q3:
            colunas_vazias = len([col for col in df_clean.columns 
                                 if df_clean[col].isnull().all()])
            st.metric("Colunas Totalmente Vazias", colunas_vazias)
        
        with col_q4:
            # Verifica se há valores extremos em colunas numéricas
            outliers = 0
            for col in numerico_cols:
                try:
                    q1 = df_clean[col].quantile(0.25)
                    q3 = df_clean[col].quantile(0.75)
                    iqr = q3 - q1
                    if iqr > 0:  # Evita divisão por zero
                        lower = q1 - 1.5 * iqr
                        upper = q3 + 1.5 * iqr
                        outliers += len(df_clean[(df_clean[col] < lower) | (df_clean[col] > upper)])
                except:
                    pass
            
            st.metric("Possíveis Outliers", outliers)
    
    # ============================================
    # RODAPÉ
    # ============================================
    st.markdown("---")
    
    col_rod1, col_rod2, col_rod3 = st.columns([2, 1, 1])
    
    with col_rod1:
        st.caption(f"📅 Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    
    with col_rod2:
        st.caption(f"📊 Dashboard Genérico - Visualizações Simples")
    
    with col_rod3:
        st.caption(f"📈 {len(df_filtered):,} registros | {len(df_clean.columns)} colunas")

if __name__ == "__main__":
    main()