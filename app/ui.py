import streamlit as st

def pdf_uploader():
    return st.file_uploader("Upload a PDF file", type=["pdf"], accept_multiple_files=True, 
                            help="Upload one or more PDF files to extract text from them.")