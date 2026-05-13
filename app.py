"""
MinOslo — DIAGNOSTIKKVERSJON
Formål: bekreft at Streamlit i det hele tatt renderer på Render.com
All CSS, API-kall og kompleks logikk er fjernet.
"""

import streamlit as st

st.set_page_config(
    page_title="MinOslo",
    page_icon="🗞️",
    layout="wide",
)

def main():
    st.title("MinOslo er oppe! 🎉")
    st.write("Hvis du ser dette, fungerer Streamlit på Render.")
    st.success("Streamlit renderer riktig.")
    st.info(f"Python og Streamlit er installert.")

if __name__ == "__main__":
    main()
