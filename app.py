import json
import streamlit as st
from financial_rag.paths import COMPANIES, MANIFEST, INDEX
from financial_rag.retrieval import Retriever
from financial_rag.llm import answer

st.set_page_config(page_title='白酒财报问答',page_icon='📊',layout='wide')
st.title('白酒财报问答 · 2024—2025')
st.caption('12 家上市公司 · 24 份官方年报 · 向量 + BM25 混合检索 · 引用可核对')

@st.cache_resource
def load_retriever(): return Retriever()

with st.sidebar:
    st.header('检索设置')
    names=[n for _,n in COMPANIES]
    companies=st.multiselect('公司（留空为全部）',names)
    years=st.multiselect('年报年度',[2024,2025],default=[2024,2025])
    labels={'混合检索':'hybrid','仅向量':'vector','仅 BM25':'bm25'}
    mode=labels[st.selectbox('索引方式',list(labels))]
    panoramic=st.checkbox('跨公司全景：逐公司检索',value=False)
    enhanced=st.checkbox('混合检索增强：术语展开与页面补全',value=True)
    k=st.slider('普通问题召回块数',4,16,8)
    st.caption('全景模式每家公司召回 2 块，显示覆盖范围。')
    st.caption('认证在本地 .env 配置。页面不会显示或收集密钥。')
    records=sorted((__import__('pathlib').Path(__file__).parent/'output/evaluation_v4').glob('*_hybrid_expanded.json'))
    if records:
        chosen=st.selectbox('查看已完成的真实实验',[p.stem for p in records])
        if st.button('载入实验记录'):
            p=next(p for p in records if p.stem==chosen)
            st.session_state['result']=json.loads(p.read_text(encoding='utf-8'))

if not (INDEX/'vectors.npy').exists():
    st.info('索引正在建立。完成后刷新本页。')
    st.stop()

with st.form('ask',border=False):
    question=st.text_area('你的问题',placeholder='例如：五粮液 2025 年营业收入和归母净利润是多少？',height=90)
    generate=st.checkbox('使用 GPT 生成带引用的回答',value=True)
    submitted=st.form_submit_button('检索并回答',type='primary')
if submitted:
    if not question.strip():
        st.warning('请先输入问题。')
        st.stop()
    retriever=load_retriever()
    with st.spinner('检索财报证据…'):
        effective_companies=companies or [n for n in names if n in question]
        effective_years=[y for y in years if str(y) in question] or years
        use_panorama=panoramic or any(w in question for w in ['12 家','12家','逐一','完整排序','几家增长'])
        if enhanced and mode=='hybrid':
            chunks=retriever.expanded(question,effective_companies or names,effective_years,use_panorama)
        else:
            chunks=(retriever.panoramic(question,effective_companies or names,effective_years,mode)
                if use_panorama else retriever.search(question,mode,k,effective_companies,effective_years))
    st.session_state['result']={'question':question,'chunks':chunks,'mode':mode,'panoramic':panoramic}
    if generate:
        try:
            with st.spinner('GPT 正在根据证据回答…'):
                st.session_state['result'].update(answer(question,chunks))
        except Exception as exc:
            st.session_state['result']['error']=str(exc)

result=st.session_state.get('result')
if result:
    chunks=result['chunks']
    st.caption('当前记录：'+result.get('id','即时问答')+' · '+result.get('mode','hybrid'))
    st.markdown('**问题：** '+result['question'])
    st.subheader('回答')
    if result.get('error'): st.error(result['error'])
    if result.get('answer'): st.markdown(result['answer'])
    else: st.info('以下为检索结果。启用 GPT 后可生成答案。')
    covered=sorted({c['company'] for c in chunks})
    st.caption(f"证据覆盖 {len(covered)} 家：{'、'.join(covered)}")
    st.subheader('出处与召回记录')
    for i,c in enumerate(chunks,1):
        with st.expander(f"[{i}] {c['company']} · {c['year']} · PDF 第 {c['page']} 页 · {c['chapter']}",expanded=i<=2):
            st.markdown(f"[打开官方 PDF]({c['url']}#page={c['page']})")
            st.code(c['text'],language=None,wrap_lines=True)
            st.caption('块 ID：'+c['id'])
    st.download_button('下载本次问答及召回记录',json.dumps(result,ensure_ascii=False,indent=2),'retrieval_record.json','application/json')
