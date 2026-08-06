"""
MACD Dual-Timeframe Backtest — Streamlit App
=============================================
Tab 1 : ETF Strategy    — Monthly filter + Weekly MACD crossover
Tab 2 : Nifty 100       — Weekly filter  + Daily  MACD crossover + Target exit

Entry  : Next candle's Open  (ETF → Monday open | Nifty 100 → next trading day open)
Costs  : Zerodha brokerage ₹20/order + STT + exchange + SEBI + stamp + GST
MTF    : Daily interest on borrowed amount at user-defined annual rate
"""

import time
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
from google.oauth2.service_account import Credentials
import gspread
import gspread.utils

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="MACD Backtest",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("📈 MACD Dual-Timeframe Backtest")
st.caption(
    "ETF Strategy (Monthly + Weekly)  |  Nifty 100 Strategy (Weekly + Daily)  |  "
    "Includes actual Zerodha costs & MTF interest"
)

RISK_FREE_RATE = 0.065  # 6.5% India — used for Sharpe / Sortino

# ─────────────────────────────────────────────────────────────
# UNIVERSE
# ─────────────────────────────────────────────────────────────

ALL_ETFS = {
    "NIFTYBEES":  "NIFTYBEES.NS",
    "JUNIORBEES": "JUNIORBEES.NS",
    "MOM100":     "MOM100.NS",
    "HDFCSML250": "HDFCSML250.NS",
    "BANKBEES":   "BANKBEES.NS",
    "ITBEES":     "ITBEES.NS",
    "PSUBNKBEES": "PSUBNKBEES.NS",
    "ICICIB22":   "ICICIB22.NS",
    "INFRABEES":  "INFRABEES.NS",
    "CONSUMBEES": "CONSUMBEES.NS",
    "PHARMABEES": "PHARMABEES.NS",
    "HEALTHIETF": "HEALTHIETF.NS",
    "MOM30IETF":  "MOM30IETF.NS",
    "ALPHA":      "ALPHA.NS",
    "MODEFENCE":  "MODEFENCE.NS",
    "ALPL30IETF": "ALPL30IETF.NS",
    "MIDCAPETF":  "MIDCAPETF.NS",
    "OILIETF":    "OILIETF.NS",
    "MOSMALL250": "MOSMALL250.NS",
    "MOVALUE":    "MOVALUE.NS",
    "GOLDBEES":   "GOLDBEES.NS",
}

NIFTY100_STOCKS = {
    "HDFCBANK":   "HDFCBANK.NS",   "RELIANCE":   "RELIANCE.NS",
    "ICICIBANK":  "ICICIBANK.NS",  "BHARTIARTL": "BHARTIARTL.NS",
    "INFY":       "INFY.NS",       "LT":         "LT.NS",
    "SBIN":       "SBIN.NS",       "ITC":        "ITC.NS",
    "AXISBANK":   "AXISBANK.NS",   "M&M":        "M&M.NS",
    "NTPC":       "NTPC.NS",       "KOTAKBANK":  "KOTAKBANK.NS",
    "TITAN":      "TITAN.NS",      "HCLTECH":    "HCLTECH.NS",
    "ONGC":       "ONGC.NS",       "ULTRACEMCO": "ULTRACEMCO.NS",
    "SUNPHARMA":  "SUNPHARMA.NS",  "MARUTI":     "MARUTI.NS",
    "BAJFINANCE": "BAJFINANCE.NS", "HINDUNILVR": "HINDUNILVR.NS",
    "WIPRO":      "WIPRO.NS",      "ADANIENT":   "ADANIENT.NS",
    "POWERGRID":  "POWERGRID.NS",  "NESTLEIND":  "NESTLEIND.NS",
    "TATASTEEL":  "TATASTEEL.NS",  "TECHM":      "TECHM.NS",
    "JSWSTEEL":   "JSWSTEEL.NS",   "COALINDIA":  "COALINDIA.NS",
    "HINDALCO":   "HINDALCO.NS",   "BAJAJFINSV": "BAJAJFINSV.NS",
    "GRASIM":     "GRASIM.NS",     "DRREDDY":    "DRREDDY.NS",
    "TCS":        "TCS.NS",        "CIPLA":      "CIPLA.NS",
    "DIVISLAB":   "DIVISLAB.NS",   "EICHERMOT":  "EICHERMOT.NS",
    "APOLLOHOSP": "APOLLOHOSP.NS", "TATACONSUM": "TATACONSUM.NS",
    "ASIANPAINT": "ASIANPAINT.NS", "BAJAJ-AUTO": "BAJAJ-AUTO.NS",
    "BRITANNIA":  "BRITANNIA.NS",  "HEROMOTOCO": "HEROMOTOCO.NS",
    "SHRIRAMFIN": "SHRIRAMFIN.NS", "BPCL":       "BPCL.NS",
    "TRENT":      "TRENT.NS",      "INDUSINDBK": "INDUSINDBK.NS",
    "LICI":       "LICI.NS",       "SBILIFE":    "SBILIFE.NS",
    "HDFCLIFE":   "HDFCLIFE.NS",   "TATAMOTORS": "TATAMOTORS.BO",
    "ADANIPORTS": "ADANIPORTS.NS", "ADANIGREEN": "ADANIGREEN.NS",
    "ADANIPOWER": "ADANIPOWER.NS", "SIEMENS":    "SIEMENS.NS",
    "HAVELLS":    "HAVELLS.NS",    "PIDILITIND": "PIDILITIND.NS",
    "BERGEPAINT": "BERGEPAINT.NS", "GODREJCP":   "GODREJCP.NS",
    "MUTHOOTFIN": "MUTHOOTFIN.NS", "CHOLAFIN":   "CHOLAFIN.NS",
    "MOTHERSON":  "MOTHERSON.NS",  "TORNTPHARM": "TORNTPHARM.NS",
    "DABUR":      "DABUR.NS",      "MARICO":     "MARICO.NS",
    "COLPAL":     "COLPAL.NS",     "LUPIN":      "LUPIN.NS",
    "BIOCON":     "BIOCON.NS",     "ICICIPRULI": "ICICIPRULI.NS",
    "ICICIGI":    "ICICIGI.NS",    "HDFCAMC":    "HDFCAMC.NS",
    "MCDOWELL-N": "MCDOWELL-N.NS", "VEDL":       "VEDL.NS",
    "ZOMATO":     "ZOMATO.NS",     "NYKAA":      "NYKAA.NS",
    "PAYTM":      "PAYTM.NS",      "DMART":      "DMART.NS",
    "AMBUJACEM":  "AMBUJACEM.NS",  "ACC":        "ACC.NS",
    "SHREECEM":   "SHREECEM.NS",   "INDIGO":     "INDIGO.NS",
    "BANKBARODA": "BANKBARODA.NS", "PNB":        "PNB.NS",
    "CANBK":      "CANBK.NS",      "UNIONBANK":  "UNIONBANK.NS",
    "NHPC":       "NHPC.NS",       "RECLTD":     "RECLTD.NS",
    "PFC":        "PFC.NS",        "IRFC":       "IRFC.NS",
    "HAL":        "HAL.NS",        "BEL":        "BEL.NS",
    "BHEL":       "BHEL.NS",       "GAIL":       "GAIL.NS",
    "IOC":        "IOC.NS",        "HINDPETRO":  "HINDPETRO.NS",
    "ZYDUSLIFE":  "ZYDUSLIFE.NS",  "ALKEM":      "ALKEM.NS",
    "PERSISTENT": "PERSISTENT.NS", "MPHASIS":    "MPHASIS.NS",
    "LTIM":       "LTIM.NS",       "OFSS":       "OFSS.NS",
}

# Nifty 500 constituents — pulled from NSE's official archive
# (archives.nseindia.com/content/indices/ind_nifty500list.csv) on 2026-08-04.
NIFTY500_STOCKS = {
    "360ONE": "360ONE.NS", "3MINDIA": "3MINDIA.NS", "AADHARHFC": "AADHARHFC.NS",
    "AARTIIND": "AARTIIND.NS", "AAVAS": "AAVAS.NS", "ABB": "ABB.NS",
    "ABBOTINDIA": "ABBOTINDIA.NS", "ABCAPITAL": "ABCAPITAL.NS", "ABDL": "ABDL.NS",
    "ABFRL": "ABFRL.NS", "ABLBL": "ABLBL.NS", "ABREL": "ABREL.NS", "ABSLAMC": "ABSLAMC.NS",
    "ACC": "ACC.NS", "ACE": "ACE.NS", "ACMESOLAR": "ACMESOLAR.NS", "ACUTAAS": "ACUTAAS.NS",
    "ADANIENSOL": "ADANIENSOL.NS", "ADANIENT": "ADANIENT.NS",
    "ADANIGREEN": "ADANIGREEN.NS", "ADANIPORTS": "ADANIPORTS.NS",
    "ADANIPOWER": "ADANIPOWER.NS", "AEGISLOG": "AEGISLOG.NS",
    "AEGISVOPAK": "AEGISVOPAK.NS", "AFCONS": "AFCONS.NS", "AFFLE": "AFFLE.NS",
    "AIAENG": "AIAENG.NS", "AIIL": "AIIL.NS", "AJANTPHARM": "AJANTPHARM.NS",
    "ALKEM": "ALKEM.NS", "AMBER": "AMBER.NS", "AMBUJACEM": "AMBUJACEM.NS",
    "ANANDRATHI": "ANANDRATHI.NS", "ANANTRAJ": "ANANTRAJ.NS", "ANGELONE": "ANGELONE.NS",
    "ANTHEM": "ANTHEM.NS", "ANURAS": "ANURAS.NS", "APARINDS": "APARINDS.NS",
    "APLAPOLLO": "APLAPOLLO.NS", "APOLLOHOSP": "APOLLOHOSP.NS",
    "APOLLOTYRE": "APOLLOTYRE.NS", "APTUS": "APTUS.NS", "ARE&M": "ARE&M.NS",
    "ASAHIINDIA": "ASAHIINDIA.NS", "ASHOKLEY": "ASHOKLEY.NS",
    "ASIANPAINT": "ASIANPAINT.NS", "ASTERDM": "ASTERDM.NS", "ASTRAL": "ASTRAL.NS",
    "ATGL": "ATGL.NS", "ATHERENERG": "ATHERENERG.NS", "ATUL": "ATUL.NS",
    "AUBANK": "AUBANK.NS", "AUROPHARMA": "AUROPHARMA.NS", "AWL": "AWL.NS",
    "AXISBANK": "AXISBANK.NS", "BAJAJ-AUTO": "BAJAJ-AUTO.NS",
    "BAJAJFINSV": "BAJAJFINSV.NS", "BAJAJHFL": "BAJAJHFL.NS",
    "BAJAJHLDNG": "BAJAJHLDNG.NS", "BAJFINANCE": "BAJFINANCE.NS",
    "BALKRISIND": "BALKRISIND.NS", "BALRAMCHIN": "BALRAMCHIN.NS",
    "BANDHANBNK": "BANDHANBNK.NS", "BANKBARODA": "BANKBARODA.NS",
    "BANKINDIA": "BANKINDIA.NS", "BATAINDIA": "BATAINDIA.NS", "BAYERCROP": "BAYERCROP.NS",
    "BBTC": "BBTC.NS", "BDL": "BDL.NS", "BEL": "BEL.NS", "BELRISE": "BELRISE.NS",
    "BEML": "BEML.NS", "BERGEPAINT": "BERGEPAINT.NS", "BHARATFORG": "BHARATFORG.NS",
    "BHARTIARTL": "BHARTIARTL.NS", "BHARTIHEXA": "BHARTIHEXA.NS", "BHEL": "BHEL.NS",
    "BIKAJI": "BIKAJI.NS", "BIOCON": "BIOCON.NS", "BLS": "BLS.NS",
    "BLUEDART": "BLUEDART.NS", "BLUEJET": "BLUEJET.NS", "BLUESTARCO": "BLUESTARCO.NS",
    "BOSCHLTD": "BOSCHLTD.NS", "BPCL": "BPCL.NS", "BRIGADE": "BRIGADE.NS",
    "BRITANNIA": "BRITANNIA.NS", "BSE": "BSE.NS", "BSOFT": "BSOFT.NS", "CAMS": "CAMS.NS",
    "CANBK": "CANBK.NS", "CANFINHOME": "CANFINHOME.NS", "CANHLIFE": "CANHLIFE.NS",
    "CAPLIPOINT": "CAPLIPOINT.NS", "CARBORUNIV": "CARBORUNIV.NS",
    "CARTRADE": "CARTRADE.NS", "CASTROLIND": "CASTROLIND.NS", "CCL": "CCL.NS",
    "CDSL": "CDSL.NS", "CEATLTD": "CEATLTD.NS", "CEMPRO": "CEMPRO.NS",
    "CENTRALBK": "CENTRALBK.NS", "CESC": "CESC.NS", "CGCL": "CGCL.NS",
    "CGPOWER": "CGPOWER.NS", "CHALET": "CHALET.NS", "CHAMBLFERT": "CHAMBLFERT.NS",
    "CHENNPETRO": "CHENNPETRO.NS", "CHOICEIN": "CHOICEIN.NS", "CHOLAFIN": "CHOLAFIN.NS",
    "CHOLAHLDNG": "CHOLAHLDNG.NS", "CIEINDIA": "CIEINDIA.NS", "CIPLA": "CIPLA.NS",
    "CLEAN": "CLEAN.NS", "COALINDIA": "COALINDIA.NS", "COCHINSHIP": "COCHINSHIP.NS",
    "COFORGE": "COFORGE.NS", "COHANCE": "COHANCE.NS", "COLPAL": "COLPAL.NS",
    "CONCOR": "CONCOR.NS", "CONCORDBIO": "CONCORDBIO.NS", "COROMANDEL": "COROMANDEL.NS",
    "CPPLUS": "CPPLUS.NS", "CRAFTSMAN": "CRAFTSMAN.NS", "CREDITACC": "CREDITACC.NS",
    "CRISIL": "CRISIL.NS", "CROMPTON": "CROMPTON.NS", "CUB": "CUB.NS",
    "CUMMINSIND": "CUMMINSIND.NS", "CYIENT": "CYIENT.NS", "DABUR": "DABUR.NS",
    "DALBHARAT": "DALBHARAT.NS", "DATAPATTNS": "DATAPATTNS.NS",
    "DCMSHRIRAM": "DCMSHRIRAM.NS", "DEEPAKFERT": "DEEPAKFERT.NS",
    "DEEPAKNTR": "DEEPAKNTR.NS", "DELHIVERY": "DELHIVERY.NS", "DEVYANI": "DEVYANI.NS",
    "DIVISLAB": "DIVISLAB.NS", "DIXON": "DIXON.NS", "DLF": "DLF.NS", "DMART": "DMART.NS",
    "DOMS": "DOMS.NS", "DRREDDY": "DRREDDY.NS", "ECLERX": "ECLERX.NS",
    "EICHERMOT": "EICHERMOT.NS", "EIDPARRY": "EIDPARRY.NS", "EIHOTEL": "EIHOTEL.NS",
    "ELECON": "ELECON.NS", "ELGIEQUIP": "ELGIEQUIP.NS", "EMAMILTD": "EMAMILTD.NS",
    "EMCURE": "EMCURE.NS", "EMMVEE": "EMMVEE.NS", "ENDURANCE": "ENDURANCE.NS",
    "ENGINERSIN": "ENGINERSIN.NS", "ENRIN": "ENRIN.NS", "ERIS": "ERIS.NS",
    "ESCORTS": "ESCORTS.NS", "ETERNAL": "ETERNAL.NS", "EXIDEIND": "EXIDEIND.NS",
    "FACT": "FACT.NS", "FEDERALBNK": "FEDERALBNK.NS", "FINCABLES": "FINCABLES.NS",
    "FIRSTCRY": "FIRSTCRY.NS", "FIVESTAR": "FIVESTAR.NS", "FLUOROCHEM": "FLUOROCHEM.NS",
    "FORCEMOT": "FORCEMOT.NS", "FORTIS": "FORTIS.NS", "FSL": "FSL.NS",
    "GABRIEL": "GABRIEL.NS", "GAIL": "GAIL.NS", "GALLANTT": "GALLANTT.NS",
    "GESHIP": "GESHIP.NS", "GICRE": "GICRE.NS", "GILLETTE": "GILLETTE.NS",
    "GLAND": "GLAND.NS", "GLAXO": "GLAXO.NS", "GLENMARK": "GLENMARK.NS",
    "GMDCLTD": "GMDCLTD.NS", "GMRAIRPORT": "GMRAIRPORT.NS", "GODFRYPHLP": "GODFRYPHLP.NS",
    "GODIGIT": "GODIGIT.NS", "GODREJCP": "GODREJCP.NS", "GODREJIND": "GODREJIND.NS",
    "GODREJPROP": "GODREJPROP.NS", "GPIL": "GPIL.NS", "GRANULES": "GRANULES.NS",
    "GRAPHITE": "GRAPHITE.NS", "GRASIM": "GRASIM.NS", "GRAVITA": "GRAVITA.NS",
    "GROWW": "GROWW.NS", "GRSE": "GRSE.NS", "GVT&D": "GVT&D.NS", "HAL": "HAL.NS",
    "HAVELLS": "HAVELLS.NS", "HBLENGINE": "HBLENGINE.NS", "HCLTECH": "HCLTECH.NS",
    "HDBFS": "HDBFS.NS", "HDFCAMC": "HDFCAMC.NS", "HDFCBANK": "HDFCBANK.NS",
    "HDFCLIFE": "HDFCLIFE.NS", "HEG": "HEG.NS", "HEROMOTOCO": "HEROMOTOCO.NS",
    "HEXT": "HEXT.NS", "HFCL": "HFCL.NS", "HINDALCO": "HINDALCO.NS",
    "HINDCOPPER": "HINDCOPPER.NS", "HINDPETRO": "HINDPETRO.NS",
    "HINDUNILVR": "HINDUNILVR.NS", "HINDZINC": "HINDZINC.NS", "HOMEFIRST": "HOMEFIRST.NS",
    "HONASA": "HONASA.NS", "HONAUT": "HONAUT.NS", "HSCL": "HSCL.NS", "HUDCO": "HUDCO.NS",
    "HYUNDAI": "HYUNDAI.NS", "ICICIAMC": "ICICIAMC.NS", "ICICIBANK": "ICICIBANK.NS",
    "ICICIGI": "ICICIGI.NS", "ICICIPRULI": "ICICIPRULI.NS", "IDBI": "IDBI.NS",
    "IDEA": "IDEA.NS", "IDFCFIRSTB": "IDFCFIRSTB.NS", "IEX": "IEX.NS", "IFCI": "IFCI.NS",
    "IGIL": "IGIL.NS", "IGL": "IGL.NS", "IIFL": "IIFL.NS", "IKS": "IKS.NS",
    "INDGN": "INDGN.NS", "INDHOTEL": "INDHOTEL.NS", "INDIACEM": "INDIACEM.NS",
    "INDIAMART": "INDIAMART.NS", "INDIANB": "INDIANB.NS", "INDIGO": "INDIGO.NS",
    "INDUSINDBK": "INDUSINDBK.NS", "INDUSTOWER": "INDUSTOWER.NS", "INFY": "INFY.NS",
    "INOXWIND": "INOXWIND.NS", "INTELLECT": "INTELLECT.NS", "IOB": "IOB.NS",
    "IOC": "IOC.NS", "IPCALAB": "IPCALAB.NS", "IRB": "IRB.NS", "IRCON": "IRCON.NS",
    "IRCTC": "IRCTC.NS", "IREDA": "IREDA.NS", "IRFC": "IRFC.NS", "ITC": "ITC.NS",
    "ITCHOTELS": "ITCHOTELS.NS", "ITI": "ITI.NS", "J&KBANK": "J&KBANK.NS",
    "JAINREC": "JAINREC.NS", "JBMA": "JBMA.NS", "JINDALSAW": "JINDALSAW.NS",
    "JINDALSTEL": "JINDALSTEL.NS", "JIOFIN": "JIOFIN.NS", "JKCEMENT": "JKCEMENT.NS",
    "JKTYRE": "JKTYRE.NS", "JMFINANCIL": "JMFINANCIL.NS", "JPPOWER": "JPPOWER.NS",
    "JSL": "JSL.NS", "JSWCEMENT": "JSWCEMENT.NS", "JSWDULUX": "JSWDULUX.NS",
    "JSWENERGY": "JSWENERGY.NS", "JSWINFRA": "JSWINFRA.NS", "JSWSTEEL": "JSWSTEEL.NS",
    "JUBLFOOD": "JUBLFOOD.NS", "JUBLINGREA": "JUBLINGREA.NS",
    "JUBLPHARMA": "JUBLPHARMA.NS", "JWL": "JWL.NS", "JYOTICNC": "JYOTICNC.NS",
    "KAJARIACER": "KAJARIACER.NS", "KALYANKJIL": "KALYANKJIL.NS",
    "KARURVYSYA": "KARURVYSYA.NS", "KAYNES": "KAYNES.NS", "KEC": "KEC.NS", "KEI": "KEI.NS",
    "KFINTECH": "KFINTECH.NS", "KIMS": "KIMS.NS", "KIRLOSENG": "KIRLOSENG.NS",
    "KOTAKBANK": "KOTAKBANK.NS", "KPIL": "KPIL.NS", "KPITTECH": "KPITTECH.NS",
    "KPRMILL": "KPRMILL.NS", "LALPATHLAB": "LALPATHLAB.NS", "LATENTVIEW": "LATENTVIEW.NS",
    "LAURUSLABS": "LAURUSLABS.NS", "LEMONTREE": "LEMONTREE.NS", "LENSKART": "LENSKART.NS",
    "LGEINDIA": "LGEINDIA.NS", "LICHSGFIN": "LICHSGFIN.NS", "LICI": "LICI.NS",
    "LINDEINDIA": "LINDEINDIA.NS", "LLOYDSME": "LLOYDSME.NS", "LODHA": "LODHA.NS",
    "LT": "LT.NS", "LTF": "LTF.NS", "LTFOODS": "LTFOODS.NS", "LTM": "LTM.NS",
    "LTTS": "LTTS.NS", "LUPIN": "LUPIN.NS", "M&M": "M&M.NS", "M&MFIN": "M&MFIN.NS",
    "MAHABANK": "MAHABANK.NS", "MANAPPURAM": "MANAPPURAM.NS", "MANKIND": "MANKIND.NS",
    "MAPMYINDIA": "MAPMYINDIA.NS", "MARICO": "MARICO.NS", "MARUTI": "MARUTI.NS",
    "MAXHEALTH": "MAXHEALTH.NS", "MAZDOCK": "MAZDOCK.NS", "MCX": "MCX.NS",
    "MEDANTA": "MEDANTA.NS", "MEESHO": "MEESHO.NS", "MFSL": "MFSL.NS", "MGL": "MGL.NS",
    "MINDACORP": "MINDACORP.NS", "MMTC": "MMTC.NS", "MOTHERSON": "MOTHERSON.NS",
    "MOTILALOFS": "MOTILALOFS.NS", "MPHASIS": "MPHASIS.NS", "MRF": "MRF.NS",
    "MRPL": "MRPL.NS", "MSUMI": "MSUMI.NS", "MUTHOOTFIN": "MUTHOOTFIN.NS",
    "NAM-INDIA": "NAM-INDIA.NS", "NATCOPHARM": "NATCOPHARM.NS",
    "NATIONALUM": "NATIONALUM.NS", "NAUKRI": "NAUKRI.NS", "NAVA": "NAVA.NS",
    "NAVINFLUOR": "NAVINFLUOR.NS", "NBCC": "NBCC.NS", "NCC": "NCC.NS",
    "NESTLEIND": "NESTLEIND.NS", "NETWEB": "NETWEB.NS", "NEULANDLAB": "NEULANDLAB.NS",
    "NEWGEN": "NEWGEN.NS", "NH": "NH.NS", "NHPC": "NHPC.NS", "NIACL": "NIACL.NS",
    "NIVABUPA": "NIVABUPA.NS", "NLCINDIA": "NLCINDIA.NS", "NMDC": "NMDC.NS",
    "NSLNISP": "NSLNISP.NS", "NTPC": "NTPC.NS", "NTPCGREEN": "NTPCGREEN.NS",
    "NUVAMA": "NUVAMA.NS", "NUVOCO": "NUVOCO.NS", "NYKAA": "NYKAA.NS",
    "OBEROIRLTY": "OBEROIRLTY.NS", "OFSS": "OFSS.NS", "OIL": "OIL.NS",
    "OLAELEC": "OLAELEC.NS", "OLECTRA": "OLECTRA.NS", "ONESOURCE": "ONESOURCE.NS",
    "ONGC": "ONGC.NS", "PAGEIND": "PAGEIND.NS", "PARADEEP": "PARADEEP.NS",
    "PATANJALI": "PATANJALI.NS", "PAYTM": "PAYTM.NS", "PCBL": "PCBL.NS",
    "PERSISTENT": "PERSISTENT.NS", "PETRONET": "PETRONET.NS", "PFC": "PFC.NS",
    "PFIZER": "PFIZER.NS", "PFOCUS": "PFOCUS.NS", "PGEL": "PGEL.NS",
    "PHOENIXLTD": "PHOENIXLTD.NS", "PIDILITIND": "PIDILITIND.NS", "PIIND": "PIIND.NS",
    "PINELABS": "PINELABS.NS", "PIRAMALFIN": "PIRAMALFIN.NS", "PNB": "PNB.NS",
    "PNBHOUSING": "PNBHOUSING.NS", "POLICYBZR": "POLICYBZR.NS", "POLYCAB": "POLYCAB.NS",
    "POLYMED": "POLYMED.NS", "POONAWALLA": "POONAWALLA.NS", "POWERGRID": "POWERGRID.NS",
    "POWERINDIA": "POWERINDIA.NS", "PPLPHARMA": "PPLPHARMA.NS",
    "PREMIERENE": "PREMIERENE.NS", "PRESTIGE": "PRESTIGE.NS", "PTCIL": "PTCIL.NS",
    "PVRINOX": "PVRINOX.NS", "PWL": "PWL.NS", "RADICO": "RADICO.NS",
    "RAILTEL": "RAILTEL.NS", "RAINBOW": "RAINBOW.NS", "RAMCOCEM": "RAMCOCEM.NS",
    "RBLBANK": "RBLBANK.NS", "RECLTD": "RECLTD.NS", "REDINGTON": "REDINGTON.NS",
    "RELIANCE": "RELIANCE.NS", "RHIM": "RHIM.NS", "RITES": "RITES.NS",
    "RKFORGE": "RKFORGE.NS", "RPOWER": "RPOWER.NS", "RRKABEL": "RRKABEL.NS",
    "RVNL": "RVNL.NS", "SAGILITY": "SAGILITY.NS", "SAIL": "SAIL.NS",
    "SAILIFE": "SAILIFE.NS", "SAMMAANCAP": "SAMMAANCAP.NS", "SAPPHIRE": "SAPPHIRE.NS",
    "SARDAEN": "SARDAEN.NS", "SAREGAMA": "SAREGAMA.NS", "SBFC": "SBFC.NS",
    "SBICARD": "SBICARD.NS", "SBILIFE": "SBILIFE.NS", "SBIN": "SBIN.NS",
    "SCHAEFFLER": "SCHAEFFLER.NS", "SCHNEIDER": "SCHNEIDER.NS", "SCI": "SCI.NS",
    "SHREECEM": "SHREECEM.NS", "SHRIRAMFIN": "SHRIRAMFIN.NS", "SHYAMMETL": "SHYAMMETL.NS",
    "SIEMENS": "SIEMENS.NS", "SIGNATURE": "SIGNATURE.NS", "SJVN": "SJVN.NS",
    "SOBHA": "SOBHA.NS", "SOLARINDS": "SOLARINDS.NS", "SONACOMS": "SONACOMS.NS",
    "SONATSOFTW": "SONATSOFTW.NS", "SPLPETRO": "SPLPETRO.NS", "SRF": "SRF.NS",
    "STARHEALTH": "STARHEALTH.NS", "SUMICHEM": "SUMICHEM.NS",
    "SUNDARMFIN": "SUNDARMFIN.NS", "SUNPHARMA": "SUNPHARMA.NS", "SUNTV": "SUNTV.NS",
    "SUPREMEIND": "SUPREMEIND.NS", "SUZLON": "SUZLON.NS", "SWANCORP": "SWANCORP.NS",
    "SWIGGY": "SWIGGY.NS", "SYNGENE": "SYNGENE.NS", "SYRMA": "SYRMA.NS",
    "TARIL": "TARIL.NS", "TATACAP": "TATACAP.NS", "TATACHEM": "TATACHEM.NS",
    "TATACOMM": "TATACOMM.NS", "TATACONSUM": "TATACONSUM.NS", "TATAELXSI": "TATAELXSI.NS",
    "TATAINVEST": "TATAINVEST.NS", "TATAPOWER": "TATAPOWER.NS",
    "TATASTEEL": "TATASTEEL.NS", "TATATECH": "TATATECH.NS", "TBOTEK": "TBOTEK.NS",
    "TCS": "TCS.NS", "TECHM": "TECHM.NS", "TECHNOE": "TECHNOE.NS", "TEGA": "TEGA.NS",
    "TEJASNET": "TEJASNET.NS", "TENNIND": "TENNIND.NS", "THELEELA": "THELEELA.NS",
    "THERMAX": "THERMAX.NS", "TIINDIA": "TIINDIA.NS", "TIMKEN": "TIMKEN.NS",
    "TITAGARH": "TITAGARH.NS", "TITAN": "TITAN.NS", "TMCV": "TMCV.NS", "TMPV": "TMPV.NS",
    "TORNTPHARM": "TORNTPHARM.NS", "TORNTPOWER": "TORNTPOWER.NS",
    "TRAVELFOOD": "TRAVELFOOD.NS", "TRENT": "TRENT.NS", "TRIDENT": "TRIDENT.NS",
    "TRITURBINE": "TRITURBINE.NS", "TTML": "TTML.NS", "TVSMOTOR": "TVSMOTOR.NS",
    "UBL": "UBL.NS", "UCOBANK": "UCOBANK.NS", "ULTRACEMCO": "ULTRACEMCO.NS",
    "UNIONBANK": "UNIONBANK.NS", "UNITDSPR": "UNITDSPR.NS", "UNOMINDA": "UNOMINDA.NS",
    "UPL": "UPL.NS", "URBANCO": "URBANCO.NS", "USHAMART": "USHAMART.NS",
    "UTIAMC": "UTIAMC.NS", "VBL": "VBL.NS", "VEDL": "VEDL.NS", "VIJAYA": "VIJAYA.NS",
    "VMM": "VMM.NS", "VOLTAS": "VOLTAS.NS", "VTL": "VTL.NS", "WAAREEENER": "WAAREEENER.NS",
    "WELCORP": "WELCORP.NS", "WELSPUNLIV": "WELSPUNLIV.NS", "WHIRLPOOL": "WHIRLPOOL.NS",
    "WIPRO": "WIPRO.NS", "WOCKPHARMA": "WOCKPHARMA.NS", "YESBANK": "YESBANK.NS",
    "ZEEL": "ZEEL.NS", "ZENSARTECH": "ZENSARTECH.NS", "ZENTEC": "ZENTEC.NS",
    "ZFCVINDIA": "ZFCVINDIA.NS", "ZYDUSLIFE": "ZYDUSLIFE.NS", "ZYDUSWELL": "ZYDUSWELL.NS",
}

# ─────────────────────────────────────────────────────────────
# DATA FETCHING  (cached per ticker + interval, 1-hour TTL)
# ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_data(ticker: str, interval: str):
    try:
        df = yf.download(ticker, period="max", interval=interval,
                         progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df is None or df.empty:
            return None
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_nifty50():
    return fetch_data("^NSEI", "1d")


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_batch_ohlc(tickers: tuple, period: str = "max"):
    """One yfinance call for a whole batch of tickers — same batching
    approach as the standalone screener scripts, to avoid per-ticker rate
    limiting when scanning large universes (e.g. all 500 Nifty 500 names)."""
    try:
        if len(tickers) == 1:
            df = yf.download(tickers[0], period=period, interval="1d",
                             progress=False, auto_adjust=True)
        else:
            df = yf.download(list(tickers), period=period, interval="1d",
                             progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df
    except Exception:
        return None


def extract_ohlc_from_batch(df: pd.DataFrame, ticker: str, single: bool):
    """Pull a clean Open/High/Low/Close frame for one ticker out of a
    (possibly multi-ticker) batch download."""
    if single:
        if all(c in df.columns for c in ["Open", "High", "Low", "Close"]):
            return df[["Open", "High", "Low", "Close"]].dropna()
        return None
    if isinstance(df.columns, pd.MultiIndex):
        cols = {}
        for label in ["Open", "High", "Low", "Close"]:
            if (label, ticker) in df.columns:
                cols[label] = df[(label, ticker)]
        if len(cols) < 4:
            return None
        return pd.DataFrame(cols).dropna()
    return None

# ─────────────────────────────────────────────────────────────
# MACD  (pre-computed on full series — no look-ahead bias
#        because EWM at index i only uses data 0..i)
# ─────────────────────────────────────────────────────────────

def calc_macd(close: pd.Series, fast: int, slow: int, sig: int):
    if len(close) < slow + sig + 3:
        return None
    ema_f  = close.ewm(span=fast, adjust=False).mean()
    ema_s  = close.ewm(span=slow, adjust=False).mean()
    macd   = ema_f - ema_s
    signal = macd.ewm(span=sig, adjust=False).mean()
    return pd.DataFrame({"macd": macd, "signal": signal}, index=close.index)

# ─────────────────────────────────────────────────────────────
# RSI / WILLIAMS %R / CCI  (Nifty 500 Momentum Screener strategy)
# ─────────────────────────────────────────────────────────────

def calc_rsi(close: pd.Series, period: int) -> pd.Series:
    """Wilder's RSI."""
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_williams_r(high: pd.Series, low: pd.Series, close: pd.Series,
                    period: int) -> pd.Series:
    hh = high.rolling(period).max()
    ll = low.rolling(period).min()
    return (hh - close) / (hh - ll) * -100


def calc_cci(source: pd.Series, period: int) -> pd.Series:
    """CCI computed on an arbitrary input series (e.g. Daily High), matching
    Chartink's generalized 'CCI Line(source, period)' function."""
    sma = source.rolling(period).mean()
    mad = source.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (source - sma) / (0.015 * mad)


def crossed_above(prev_val: float, curr_val: float, level: float) -> bool:
    return prev_val <= level and curr_val > level


def crossed_below(prev_val: float, curr_val: float, level: float) -> bool:
    return prev_val >= level and curr_val < level


def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Wilder's Average True Range — same smoothing method as calc_rsi, for
    consistency. True Range on day i = max(high-low, |high - prev close|,
    |low - prev close|); ATR is its Wilder-smoothed moving average."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def convert_to_heiken_ashi(ohlc: pd.DataFrame) -> pd.DataFrame:
    """Heikin-Ashi OHLC from a raw daily Open/High/Low/Close frame."""
    ha = ohlc[["Open", "High", "Low", "Close"]].copy()
    ha["HA_Close"] = (ha["Open"] + ha["High"] + ha["Low"] + ha["Close"]) / 4

    ha_open = [(ha["Open"].iloc[0] + ha["Close"].iloc[0]) / 2]
    for i in range(1, len(ha)):
        ha_open.append((ha_open[i - 1] + ha["HA_Close"].iloc[i - 1]) / 2)
    ha["HA_Open"] = ha_open

    ha["HA_High"] = ha[["High", "HA_Open", "HA_Close"]].max(axis=1)
    ha["HA_Low"]  = ha[["Low", "HA_Open", "HA_Close"]].min(axis=1)
    return ha[["HA_Open", "HA_High", "HA_Low", "HA_Close"]]


def calc_pct_from_ath(high: pd.Series, close: pd.Series) -> pd.Series:
    """% below all-time-high-so-far, as of each day — uses an expanding
    max (cummax), never the full-series max, so there's no look-ahead:
    day i only ever sees the ATH known up to day i."""
    ath_so_far = high.cummax()
    return (ath_so_far - close) / ath_so_far * 100


def calc_roc(close: pd.Series, period: int) -> pd.Series:
    return (close - close.shift(period)) / close.shift(period) * 100

# ─────────────────────────────────────────────────────────────
# TRANSACTION COSTS  (Zerodha, delivery / MTF)
# ─────────────────────────────────────────────────────────────

def txn_costs(qty: int, entry: float, exit_p: float) -> float:
    """Full round-trip cost: brokerage + STT + exchange + SEBI + stamp + GST."""
    buy_val  = qty * entry
    sell_val = qty * exit_p
    turnover = buy_val + sell_val

    brokerage = 40.0                      # ₹20 per leg × 2
    stt       = 0.001  * sell_val         # 0.1% on sell side (delivery)
    exchange  = 0.0000335 * turnover      # NSE transaction charge
    sebi      = 0.000001  * turnover      # SEBI charges
    stamp     = 0.00015   * buy_val       # Stamp duty on buy
    gst       = 0.18 * (brokerage + exchange + sebi)

    return brokerage + stt + exchange + sebi + stamp + gst


def mtf_cost(entry: float, qty: int, leverage: int,
             days: int, annual_rate: float) -> float:
    """Daily MTF interest on borrowed amount for holding period."""
    if leverage <= 1:
        return 0.0
    position_val = entry * qty
    borrowed     = position_val * (leverage - 1) / leverage
    return borrowed * (annual_rate / 365) * days

# ─────────────────────────────────────────────────────────────
# ETF BACKTEST ENGINE
# Entry : Monthly MACD > Signal (trend filter)
#         + Weekly MACD crosses ABOVE Signal  → enter next week's open
# Exit  : Weekly MACD crosses BELOW Signal    → exit  next week's open
# ─────────────────────────────────────────────────────────────

def run_etf_backtest(etf_dict, fast, slow, sig_p, cash, leverage, rate,
                     start_date=None, end_date=None,
                     use_htf_filter=True, entry_trigger="crossover",
                     exit_trigger="crossover", sma_period=0,
                     stop_loss_pct=0.0, target_pct=0.0, trailing_stop_pct=0.0):
    trades, failed = [], []
    lookback = slow + sig_p + 2
    prog = st.progress(0)
    stat = st.empty()

    for n, (sym, ticker) in enumerate(etf_dict.items()):
        stat.text(f"Fetching {sym}  ({n+1}/{len(etf_dict)})...")
        prog.progress((n + 1) / len(etf_dict))

        wk = fetch_data(ticker, "1wk")
        mo = fetch_data(ticker, "1mo")

        if wk is None or mo is None:
            failed.append(sym)
            continue

        if start_date is not None:
            wk = wk[wk.index >= start_date]
            mo = mo[mo.index >= start_date]
        if end_date is not None:
            wk = wk[wk.index <= end_date]
            mo = mo[mo.index <= end_date]

        if len(wk) < lookback + 2:
            failed.append(sym)
            continue

        wk_m = calc_macd(wk["Close"].dropna(), fast, slow, sig_p)
        mo_m = calc_macd(mo["Close"].dropna(), fast, slow, sig_p)
        if wk_m is None or mo_m is None:
            failed.append(sym)
            continue

        in_pos, ep, ed, qty_, peak_p = False, 0.0, None, 0, 0.0

        for i in range(lookback, len(wk) - 1):
            w_date = wk.index[i]

            if not in_pos:
                # Higher timeframe filter (configurable)
                if use_htf_filter:
                    mo_slice = mo_m[mo_m.index <= w_date]
                    if len(mo_slice) < 2:
                        continue
                    if mo_slice["macd"].iloc[-1] <= mo_slice["signal"].iloc[-1]:
                        continue

                # SMA price filter (configurable)
                if sma_period > 0:
                    sma_val = wk["Close"].rolling(sma_period).mean().iloc[i]
                    if pd.isna(sma_val) or wk["Close"].iloc[i] <= sma_val:
                        continue

                # Weekly entry trigger (configurable)
                pm = wk_m["macd"].iloc[i - 1];   ps = wk_m["signal"].iloc[i - 1]
                cm = wk_m["macd"].iloc[i];        cs = wk_m["signal"].iloc[i]
                if pd.isna(pm) or pd.isna(cm):
                    continue
                if entry_trigger == "crossover":
                    entry_ok = pm <= ps and cm > cs
                elif entry_trigger == "above_signal":
                    entry_ok = cm > cs
                else:  # above_zero
                    entry_ok = pm <= 0 and cm > 0
                if not entry_ok:
                    continue

                next_open = wk["Open"].iloc[i + 1]
                if pd.isna(next_open) or float(next_open) <= 0:
                    continue

                qty_ = int((cash * leverage) // float(next_open))
                if qty_ <= 0:
                    continue

                ep, ed, in_pos = float(next_open), wk.index[i + 1], True
                peak_p = ep

            else:
                curr_close = float(wk["Close"].iloc[i])

                # Update trailing stop peak
                if curr_close > peak_p:
                    peak_p = curr_close

                # Price-based exits
                stop_hit   = stop_loss_pct    > 0 and curr_close <= ep     * (1 - stop_loss_pct)
                target_hit = target_pct        > 0 and curr_close >= ep     * (1 + target_pct)
                trail_hit  = trailing_stop_pct > 0 and curr_close <= peak_p * (1 - trailing_stop_pct)

                # MACD exit trigger (configurable)
                pm = wk_m["macd"].iloc[i - 1];   ps = wk_m["signal"].iloc[i - 1]
                cm = wk_m["macd"].iloc[i];        cs = wk_m["signal"].iloc[i]
                if pd.isna(pm) or pd.isna(cm):
                    macd_exit = False
                elif exit_trigger == "crossover":
                    macd_exit = pm >= ps and cm < cs
                elif exit_trigger == "below_signal":
                    macd_exit = cm < cs
                else:  # below_zero
                    macd_exit = pm >= 0 and cm < 0

                if not (stop_hit or target_hit or trail_hit or macd_exit):
                    continue

                if stop_hit:       exit_reason = "STOP_LOSS"
                elif target_hit:   exit_reason = "TARGET"
                elif trail_hit:    exit_reason = "TRAIL_STOP"
                else:              exit_reason = "MACD_EXIT"

                xp   = float(wk["Open"].iloc[i + 1])
                xd   = wk.index[i + 1]
                days = max((xd - ed).days, 1)
                gp   = (xp - ep) * qty_
                cst  = txn_costs(qty_, ep, xp)
                mti  = mtf_cost(ep, qty_, leverage, days, rate)
                np_  = gp - cst - mti
                cash_used = ep * qty_ / leverage

                trades.append(dict(
                    symbol=sym, entry_date=ed, exit_date=xd,
                    entry_price=round(ep, 2), exit_price=round(xp, 2),
                    qty=qty_, holding_days=days, exit_reason=exit_reason,
                    gross_pnl=round(gp, 2), costs=round(cst, 2),
                    mtf_interest=round(mti, 2), net_pnl=round(np_, 2),
                    return_pct=round(np_ / cash_used * 100, 2),
                    status="CLOSED",
                ))
                in_pos, ep, ed, qty_, peak_p = False, 0.0, None, 0, 0.0

        if in_pos:
            xp   = float(wk["Close"].iloc[-1])
            xd   = wk.index[-1]
            days = max((xd - ed).days, 1)
            gp   = (xp - ep) * qty_
            cst  = txn_costs(qty_, ep, xp)
            mti  = mtf_cost(ep, qty_, leverage, days, rate)
            np_  = gp - cst - mti
            cash_used = ep * qty_ / leverage
            trades.append(dict(
                symbol=sym, entry_date=ed, exit_date=xd,
                entry_price=round(ep, 2), exit_price=round(xp, 2),
                qty=qty_, holding_days=days, exit_reason="OPEN",
                gross_pnl=round(gp, 2), costs=round(cst, 2),
                mtf_interest=round(mti, 2), net_pnl=round(np_, 2),
                return_pct=round(np_ / cash_used * 100, 2),
                status="OPEN (MTM)",
            ))

        time.sleep(0.25)

    prog.empty()
    stat.empty()
    return pd.DataFrame(trades), failed

# ─────────────────────────────────────────────────────────────
# NIFTY 100 BACKTEST ENGINE
# Entry : Weekly MACD > Signal (trend filter)
#         + Daily MACD crosses ABOVE Signal   → enter next day's open
# Exit  : Daily MACD crosses BELOW Signal     → exit next day's open
#         OR last close >= entry × (1 + target%) → exit next day's open
# ─────────────────────────────────────────────────────────────

def run_nifty100_backtest(stock_dict, fast, slow, sig_p, cash,
                          leverage, rate, target_pct,
                          start_date=None, end_date=None,
                          use_htf_filter=True, entry_trigger="crossover",
                          exit_trigger="crossover", sma_period=0,
                          stop_loss_pct=0.0, trailing_stop_pct=0.0):
    trades, failed = [], []
    lookback = slow + sig_p + 2
    prog = st.progress(0)
    stat = st.empty()

    for n, (sym, ticker) in enumerate(stock_dict.items()):
        stat.text(f"Fetching {sym}  ({n+1}/{len(stock_dict)})...")
        prog.progress((n + 1) / len(stock_dict))

        dy = fetch_data(ticker, "1d")
        wk = fetch_data(ticker, "1wk")

        if dy is None or wk is None:
            failed.append(sym)
            continue

        if start_date is not None:
            dy = dy[dy.index >= start_date]
            wk = wk[wk.index >= start_date]
        if end_date is not None:
            dy = dy[dy.index <= end_date]
            wk = wk[wk.index <= end_date]

        if len(dy) < lookback + 2:
            failed.append(sym)
            continue

        dy_m = calc_macd(dy["Close"].dropna(), fast, slow, sig_p)
        wk_m = calc_macd(wk["Close"].dropna(), fast, slow, sig_p)
        if dy_m is None or wk_m is None:
            failed.append(sym)
            continue

        in_pos, ep, ed, qty_, peak_p = False, 0.0, None, 0, 0.0

        for i in range(lookback, len(dy) - 1):
            d_date = dy.index[i]

            if not in_pos:
                # Higher timeframe filter (configurable)
                if use_htf_filter:
                    wk_slice = wk_m[wk_m.index <= d_date]
                    if len(wk_slice) < 2:
                        continue
                    if wk_slice["macd"].iloc[-1] <= wk_slice["signal"].iloc[-1]:
                        continue

                # SMA price filter (configurable)
                if sma_period > 0:
                    sma_val = dy["Close"].rolling(sma_period).mean().iloc[i]
                    if pd.isna(sma_val) or dy["Close"].iloc[i] <= sma_val:
                        continue

                # Daily entry trigger (configurable)
                pm = dy_m["macd"].iloc[i - 1];   ps = dy_m["signal"].iloc[i - 1]
                cm = dy_m["macd"].iloc[i];        cs = dy_m["signal"].iloc[i]
                if pd.isna(pm) or pd.isna(cm):
                    continue
                if entry_trigger == "crossover":
                    entry_ok = pm <= ps and cm > cs
                elif entry_trigger == "above_signal":
                    entry_ok = cm > cs
                else:  # above_zero
                    entry_ok = pm <= 0 and cm > 0
                if not entry_ok:
                    continue

                next_open = dy["Open"].iloc[i + 1]
                if pd.isna(next_open) or float(next_open) <= 0:
                    continue

                qty_ = int((cash * leverage) // float(next_open))
                if qty_ <= 0:
                    continue

                ep, ed, in_pos = float(next_open), dy.index[i + 1], True
                peak_p = ep

            else:
                curr_close = float(dy["Close"].iloc[i])

                # Update trailing stop peak
                if curr_close > peak_p:
                    peak_p = curr_close

                # Price-based exits
                stop_hit   = stop_loss_pct    > 0 and curr_close <= ep     * (1 - stop_loss_pct)
                target_hit = target_pct        > 0 and curr_close >= ep     * (1 + target_pct)
                trail_hit  = trailing_stop_pct > 0 and curr_close <= peak_p * (1 - trailing_stop_pct)

                # MACD exit trigger (configurable)
                pm = dy_m["macd"].iloc[i - 1];   ps = dy_m["signal"].iloc[i - 1]
                cm = dy_m["macd"].iloc[i];        cs = dy_m["signal"].iloc[i]
                if pd.isna(pm) or pd.isna(cm):
                    macd_exit = False
                elif exit_trigger == "crossover":
                    macd_exit = pm >= ps and cm < cs
                elif exit_trigger == "below_signal":
                    macd_exit = cm < cs
                else:  # below_zero
                    macd_exit = pm >= 0 and cm < 0

                if not (stop_hit or target_hit or trail_hit or macd_exit):
                    continue

                if stop_hit:       reason = "STOP_LOSS"
                elif target_hit:   reason = "TARGET"
                elif trail_hit:    reason = "TRAIL_STOP"
                else:              reason = "MACD_EXIT"

                xp     = float(dy["Open"].iloc[i + 1])
                xd     = dy.index[i + 1]
                days   = max((xd - ed).days, 1)
                gp     = (xp - ep) * qty_
                cst    = txn_costs(qty_, ep, xp)
                mti    = mtf_cost(ep, qty_, leverage, days, rate)
                np_    = gp - cst - mti
                cash_used = ep * qty_ / leverage

                trades.append(dict(
                    symbol=sym, entry_date=ed, exit_date=xd,
                    entry_price=round(ep, 2), exit_price=round(xp, 2),
                    qty=qty_, holding_days=days, exit_reason=reason,
                    gross_pnl=round(gp, 2), costs=round(cst, 2),
                    mtf_interest=round(mti, 2), net_pnl=round(np_, 2),
                    return_pct=round(np_ / cash_used * 100, 2),
                    status="CLOSED",
                ))
                in_pos, ep, ed, qty_, peak_p = False, 0.0, None, 0, 0.0

        if in_pos:
            xp   = float(dy["Close"].iloc[-1])
            xd   = dy.index[-1]
            days = max((xd - ed).days, 1)
            gp   = (xp - ep) * qty_
            cst  = txn_costs(qty_, ep, xp)
            mti  = mtf_cost(ep, qty_, leverage, days, rate)
            np_  = gp - cst - mti
            cash_used = ep * qty_ / leverage
            trades.append(dict(
                symbol=sym, entry_date=ed, exit_date=xd,
                entry_price=round(ep, 2), exit_price=round(xp, 2),
                qty=qty_, holding_days=days, exit_reason="OPEN",
                gross_pnl=round(gp, 2), costs=round(cst, 2),
                mtf_interest=round(mti, 2), net_pnl=round(np_, 2),
                return_pct=round(np_ / cash_used * 100, 2),
                status="OPEN (MTM)",
            ))

        time.sleep(0.1)

    prog.empty()
    stat.empty()
    return pd.DataFrame(trades), failed

# ─────────────────────────────────────────────────────────────
# NIFTY 500 MOMENTUM SCREENER BACKTEST ENGINE
# Entry : Daily RSI, Williams %R and CCI (on Daily High) ALL cross above
#         their thresholds on the same day  → enter next day's open
# Exit  : Target % hit  OR  Stop-loss % hit  OR  Trailing-stop % hit
#         OR  max holding days reached  OR  (optional) RSI crosses back
#         below a reversal level  → exit next day's open
# ─────────────────────────────────────────────────────────────

SCREENER_BATCH_SIZE            = 20   # tickers per yfinance batch call
SCREENER_SLEEP_BETWEEN_BATCHES = 2.0  # seconds between batch downloads


def fetch_screener_universe(stock_dict, prog=None, stat=None):
    """Batch-download daily OHLC for the whole universe (e.g. all 500 Nifty
    500 names) using the same batching pattern as the standalone screener
    script — a handful of tickers per yfinance call instead of one call per
    ticker, so scanning the full universe doesn't trip Yahoo Finance's rate
    limiter. Falls back to the per-ticker cached fetch for any symbol that
    comes back empty in its batch. Returns (ohlc_map, failed)."""
    items = list(stock_dict.items())
    total_batches = (len(items) - 1) // SCREENER_BATCH_SIZE + 1
    ohlc_map, failed = {}, []

    for b_start in range(0, len(items), SCREENER_BATCH_SIZE):
        batch = items[b_start:b_start + SCREENER_BATCH_SIZE]
        b_num = b_start // SCREENER_BATCH_SIZE + 1
        tickers = tuple(t for _, t in batch)

        if stat is not None:
            stat.text(f"Fetching batch {b_num}/{total_batches} "
                      f"({len(tickers)} symbols)...")
        if prog is not None:
            prog.progress(min(1.0, (b_start + len(batch)) / len(items)))

        batch_df = fetch_batch_ohlc(tickers, period="max")
        single = len(tickers) == 1

        for sym, ticker in batch:
            ohlc = None
            if batch_df is not None:
                ohlc = extract_ohlc_from_batch(batch_df, ticker, single)
            if ohlc is None or ohlc.empty:
                # Missing from the batch — fall back to an individual,
                # separately-cached download rather than failing outright.
                dy = fetch_data(ticker, "1d")
                if dy is not None and all(c in dy.columns for c in
                                          ["Open", "High", "Low", "Close"]):
                    ohlc = dy[["Open", "High", "Low", "Close"]].dropna()
            if ohlc is None or ohlc.empty:
                failed.append(sym)
                continue
            ohlc_map[sym] = ohlc

        if b_start + SCREENER_BATCH_SIZE < len(items):
            time.sleep(SCREENER_SLEEP_BETWEEN_BATCHES)

    return ohlc_map, failed


def run_screener_backtest(stock_dict, rsi_period, rsi_level, wr_period, wr_level,
                          cci_period, cci_level, cash, leverage, rate,
                          start_date=None, end_date=None,
                          target_pct=0.05, stop_loss_pct=0.0, trailing_stop_pct=0.0,
                          max_hold_days=0, use_rsi_exit=False, rsi_exit_level=50.0,
                          use_prev_low_stop=False,
                          use_atr_stop=False, atr_period=14, atr_mult=1.5,
                          use_atr_trail=False, atr_trail_period=14, atr_trail_mult=3.0,
                          use_macd_exit=False, macd_fast=12, macd_slow=24, macd_sig=6):
    trades = []
    lookback = max(rsi_period, wr_period, cci_period, atr_period,
                   atr_trail_period, macd_slow + macd_sig) + 2
    prog = st.progress(0)
    stat = st.empty()

    ohlc_map, failed = fetch_screener_universe(stock_dict, prog=prog, stat=stat)

    stat.text(f"Fetched {len(ohlc_map)}/{len(stock_dict)} symbols — running backtest...")

    for sym, dy in ohlc_map.items():
        if start_date is not None:
            dy = dy[dy.index >= start_date]
        if end_date is not None:
            dy = dy[dy.index <= end_date]

        if len(dy) < lookback + 2:
            failed.append(sym)
            continue

        close = dy["Close"].dropna()
        high  = dy["High"]
        low   = dy["Low"]

        rsi = calc_rsi(close, rsi_period)
        wr  = calc_williams_r(high, low, close, wr_period)
        cci = calc_cci(high, cci_period)
        atr = calc_atr(high, low, close, atr_period)
        atr_trail = calc_atr(high, low, close, atr_trail_period)
        macd_df = calc_macd(close, macd_fast, macd_slow, macd_sig)

        in_pos, ep, ed, qty_, peak_p, atr_e = False, 0.0, None, 0, 0.0, 0.0

        for i in range(lookback, len(dy) - 1):
            if not in_pos:
                r_p, r_c = rsi.iloc[i - 1], rsi.iloc[i]
                w_p, w_c = wr.iloc[i - 1], wr.iloc[i]
                c_p, c_c = cci.iloc[i - 1], cci.iloc[i]
                if pd.isna(r_p) or pd.isna(r_c) or pd.isna(w_p) or pd.isna(w_c) \
                        or pd.isna(c_p) or pd.isna(c_c):
                    continue

                entry_ok = (crossed_above(r_p, r_c, rsi_level) and
                            crossed_above(w_p, w_c, wr_level) and
                            crossed_above(c_p, c_c, cci_level))
                if not entry_ok:
                    continue

                next_open = dy["Open"].iloc[i + 1]
                if pd.isna(next_open) or float(next_open) <= 0:
                    continue

                qty_ = int((cash * leverage) // float(next_open))
                if qty_ <= 0:
                    continue

                ep, ed, in_pos = float(next_open), dy.index[i + 1], True
                peak_p = ep
                atr_e  = float(atr.iloc[i]) if not pd.isna(atr.iloc[i]) else 0.0

            else:
                curr_close = float(dy["Close"].iloc[i])
                if curr_close > peak_p:
                    peak_p = curr_close

                stop_hit   = stop_loss_pct    > 0 and curr_close <= ep     * (1 - stop_loss_pct)
                target_hit = target_pct        > 0 and curr_close >= ep     * (1 + target_pct)
                trail_hit  = trailing_stop_pct > 0 and curr_close <= peak_p * (1 - trailing_stop_pct)

                atr_stop_hit = (use_atr_stop and atr_e > 0
                                and curr_close <= ep - atr_mult * atr_e)

                atr_trail_hit = False
                if use_atr_trail:
                    curr_atr_trail = atr_trail.iloc[i]
                    if not pd.isna(curr_atr_trail):
                        atr_trail_hit = curr_close <= peak_p - atr_trail_mult * float(curr_atr_trail)

                macd_exit_hit = False
                if use_macd_exit and macd_df is not None:
                    pm = macd_df["macd"].iloc[i - 1];   ps = macd_df["signal"].iloc[i - 1]
                    cm = macd_df["macd"].iloc[i];        cs = macd_df["signal"].iloc[i]
                    if not (pd.isna(pm) or pd.isna(cm)):
                        macd_exit_hit = pm >= ps and cm < cs

                prev_low_hit = False
                if use_prev_low_stop and not target_hit:
                    prev_low_hit = float(dy["Low"].iloc[i]) <= float(dy["Low"].iloc[i - 1])

                days_held = (dy.index[i] - ed).days
                time_hit  = max_hold_days > 0 and days_held >= max_hold_days

                rsi_exit_hit = False
                if use_rsi_exit:
                    r_p, r_c = rsi.iloc[i - 1], rsi.iloc[i]
                    if not (pd.isna(r_p) or pd.isna(r_c)):
                        rsi_exit_hit = crossed_below(r_p, r_c, rsi_exit_level)

                if not (stop_hit or target_hit or trail_hit or atr_stop_hit
                        or atr_trail_hit or macd_exit_hit
                        or prev_low_hit or time_hit or rsi_exit_hit):
                    continue

                if stop_hit:         exit_reason = "STOP_LOSS"
                elif target_hit:     exit_reason = "TARGET"
                elif trail_hit:      exit_reason = "TRAIL_STOP"
                elif atr_stop_hit:   exit_reason = "ATR_STOP"
                elif atr_trail_hit:  exit_reason = "ATR_TRAIL"
                elif macd_exit_hit:  exit_reason = "MACD_EXIT"
                elif prev_low_hit:   exit_reason = "PREV_LOW_BREAK"
                elif time_hit:       exit_reason = "TIME_EXIT"
                else:                exit_reason = "RSI_EXIT"

                xp   = float(dy["Open"].iloc[i + 1])
                xd   = dy.index[i + 1]
                days = max((xd - ed).days, 1)
                gp   = (xp - ep) * qty_
                cst  = txn_costs(qty_, ep, xp)
                mti  = mtf_cost(ep, qty_, leverage, days, rate)
                np_  = gp - cst - mti
                cash_used = ep * qty_ / leverage

                trades.append(dict(
                    symbol=sym, entry_date=ed, exit_date=xd,
                    entry_price=round(ep, 2), exit_price=round(xp, 2),
                    qty=qty_, holding_days=days, exit_reason=exit_reason,
                    gross_pnl=round(gp, 2), costs=round(cst, 2),
                    mtf_interest=round(mti, 2), net_pnl=round(np_, 2),
                    return_pct=round(np_ / cash_used * 100, 2),
                    status="CLOSED",
                ))
                in_pos, ep, ed, qty_, peak_p, atr_e = False, 0.0, None, 0, 0.0, 0.0

        if in_pos:
            xp   = float(dy["Close"].iloc[-1])
            xd   = dy.index[-1]
            days = max((xd - ed).days, 1)
            gp   = (xp - ep) * qty_
            cst  = txn_costs(qty_, ep, xp)
            mti  = mtf_cost(ep, qty_, leverage, days, rate)
            np_  = gp - cst - mti
            cash_used = ep * qty_ / leverage
            trades.append(dict(
                symbol=sym, entry_date=ed, exit_date=xd,
                entry_price=round(ep, 2), exit_price=round(xp, 2),
                qty=qty_, holding_days=days, exit_reason="OPEN",
                gross_pnl=round(gp, 2), costs=round(cst, 2),
                mtf_interest=round(mti, 2), net_pnl=round(np_, 2),
                return_pct=round(np_ / cash_used * 100, 2),
                status="OPEN (MTM)",
            ))

    prog.empty()
    stat.empty()
    return pd.DataFrame(trades), failed

# ─────────────────────────────────────────────────────────────
# N200 HEIKIN-ASHI MACD STRATEGY  (replicates n200_MACD.py's screener)
# Entry — Stage 1 (Consider) AND Stage 2 (Ready for Ranking) must BOTH
# confirm together, every time, exactly matching the real trading
# process (no separate/optional trigger — entering on Stage 1 alone
# was a bug in the first version of this engine):
#   Stage 1: % from ATH < pct_ath_max, Monthly HA-MACD(12,24,3) > Signal,
#            Monthly HA-ROC(6) > 0, Weekly HA-MACD(12,24,3) > Signal
#   Stage 2: this week's weekly MACD-Signal gap > 0.85x last week's gap,
#            AND last week's gap was already > 0 (sustained 2+ weeks,
#            not a one-week blip)
# Exit : Weekly HA-MACD(12,24,3) reverse crossover (configurable),
#        + optional stop/target/trailing/time-cap
# Fills always use raw (non-Heikin-Ashi) weekly Open/Close — HA is a
# signal-smoothing construct, never a tradable price.
# ─────────────────────────────────────────────────────────────

def run_n200_backtest(stock_dict, cash, leverage, rate,
                      start_date=None, end_date=None,
                      pct_ath_max=25.0,
                      exit_trigger="crossover",
                      target_pct=0.0, stop_loss_pct=0.0, trailing_stop_pct=0.0,
                      max_hold_days=0,
                      collect_signals=False):
    trades, failed = [], []
    signals = []   # every week Stage 1 + Stage 2 both confirm, whether or
                    # not a trade was actually taken that week (audit log)
    lookback = 24 + 3 + 2   # weekly MACD(12,24,3) warm-up
    prog = st.progress(0)
    stat = st.empty()

    ohlc_map, failed = fetch_screener_universe(stock_dict, prog=prog, stat=stat)

    stat.text(f"Fetched {len(ohlc_map)}/{len(stock_dict)} symbols — running backtest...")

    for sym, dy in ohlc_map.items():
        if start_date is not None:
            dy = dy[dy.index >= start_date]
        if end_date is not None:
            dy = dy[dy.index <= end_date]

        if len(dy) < 100:
            failed.append(sym)
            continue

        pct_ath_daily = calc_pct_from_ath(dy["High"], dy["Close"])
        pct_ath_wk = pct_ath_daily.resample("W-FRI").last().dropna()

        wk_raw = dy.resample("W-FRI").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
        ).dropna()

        ha = convert_to_heiken_ashi(dy)
        wk_ha = ha.resample("W-FRI").agg(
            {"HA_Open": "first", "HA_High": "max", "HA_Low": "min", "HA_Close": "last"}
        ).dropna()
        mo_ha = ha.resample("ME").agg(
            {"HA_Open": "first", "HA_High": "max", "HA_Low": "min", "HA_Close": "last"}
        ).dropna()

        if len(wk_raw) < lookback + 2 or len(wk_ha) < lookback + 2:
            failed.append(sym)
            continue

        wk_m = calc_macd(wk_ha["HA_Close"], 12, 24, 3)
        mo_m = calc_macd(mo_ha["HA_Close"], 12, 24, 3)
        mo_roc = calc_roc(mo_ha["HA_Close"], 6)
        if wk_m is None or mo_m is None:
            failed.append(sym)
            continue

        in_pos, ep, ed, qty_, peak_p = False, 0.0, None, 0, 0.0

        for i in range(lookback, len(wk_raw) - 1):
            w_date = wk_raw.index[i]

            # ── Evaluate Stage 1 + Stage 2 for THIS week, regardless of
            #    in_pos, so the audit log captures every historical signal
            #    even for weeks the backtest happened to already be holding
            #    a position from an earlier entry. ──
            mo_slice  = mo_m[mo_m.index <= w_date]
            roc_slice = mo_roc[mo_roc.index <= w_date].dropna()
            pm = wk_m["macd"].iloc[i - 1];   ps = wk_m["signal"].iloc[i - 1]
            cm = wk_m["macd"].iloc[i];        cs = wk_m["signal"].iloc[i]

            stage1_ok = (
                len(mo_slice) >= 2 and len(roc_slice) >= 1
                and not pd.isna(pm) and not pd.isna(cm)
                and i < len(pct_ath_wk) and not pd.isna(pct_ath_wk.iloc[i])
                and mo_slice["macd"].iloc[-1] > mo_slice["signal"].iloc[-1]
                and float(roc_slice.iloc[-1]) > 0
                and float(pct_ath_wk.iloc[i]) < pct_ath_max
                and cm > cs
            )
            stage2_ok = False
            if stage1_ok:
                prev_gap = pm - ps
                curr_gap = cm - cs
                stage2_ok = curr_gap > 0.85 * prev_gap and prev_gap > 0

            if collect_signals and stage1_ok and stage2_ok:
                signals.append(dict(
                    symbol=sym, week=w_date,
                    monthly_macd=round(float(mo_slice["macd"].iloc[-1]), 4),
                    monthly_signal=round(float(mo_slice["signal"].iloc[-1]), 4),
                    monthly_roc=round(float(roc_slice.iloc[-1]), 2),
                    pct_from_ath=round(float(pct_ath_wk.iloc[i]), 2),
                    weekly_macd=round(float(cm), 4),
                    weekly_signal=round(float(cs), 4),
                ))

            if not in_pos:
                if not (stage1_ok and stage2_ok):
                    continue

                next_open = wk_raw["Open"].iloc[i + 1]
                if pd.isna(next_open) or float(next_open) <= 0:
                    continue

                qty_ = int((cash * leverage) // float(next_open))
                if qty_ <= 0:
                    continue

                ep, ed, in_pos = float(next_open), wk_raw.index[i + 1], True
                peak_p = ep

            else:
                curr_close = float(wk_raw["Close"].iloc[i])
                if curr_close > peak_p:
                    peak_p = curr_close

                stop_hit   = stop_loss_pct    > 0 and curr_close <= ep     * (1 - stop_loss_pct)
                target_hit = target_pct        > 0 and curr_close >= ep     * (1 + target_pct)
                trail_hit  = trailing_stop_pct > 0 and curr_close <= peak_p * (1 - trailing_stop_pct)

                days_held = (wk_raw.index[i] - ed).days
                time_hit  = max_hold_days > 0 and days_held >= max_hold_days

                pm = wk_m["macd"].iloc[i - 1];   ps = wk_m["signal"].iloc[i - 1]
                cm = wk_m["macd"].iloc[i];        cs = wk_m["signal"].iloc[i]
                if pd.isna(pm) or pd.isna(cm):
                    macd_exit = False
                elif exit_trigger == "crossover":
                    macd_exit = pm >= ps and cm < cs
                elif exit_trigger == "below_signal":
                    macd_exit = cm < cs
                else:  # below_zero
                    macd_exit = pm >= 0 and cm < 0

                if not (stop_hit or target_hit or trail_hit or time_hit or macd_exit):
                    continue

                if stop_hit:       exit_reason = "STOP_LOSS"
                elif target_hit:   exit_reason = "TARGET"
                elif trail_hit:    exit_reason = "TRAIL_STOP"
                elif time_hit:     exit_reason = "TIME_EXIT"
                else:              exit_reason = "MACD_EXIT"

                xp   = float(wk_raw["Open"].iloc[i + 1])
                xd   = wk_raw.index[i + 1]
                days = max((xd - ed).days, 1)
                gp   = (xp - ep) * qty_
                cst  = txn_costs(qty_, ep, xp)
                mti  = mtf_cost(ep, qty_, leverage, days, rate)
                np_  = gp - cst - mti
                cash_used = ep * qty_ / leverage

                trades.append(dict(
                    symbol=sym, entry_date=ed, exit_date=xd,
                    entry_price=round(ep, 2), exit_price=round(xp, 2),
                    qty=qty_, holding_days=days, exit_reason=exit_reason,
                    gross_pnl=round(gp, 2), costs=round(cst, 2),
                    mtf_interest=round(mti, 2), net_pnl=round(np_, 2),
                    return_pct=round(np_ / cash_used * 100, 2),
                    status="CLOSED",
                ))
                in_pos, ep, ed, qty_, peak_p = False, 0.0, None, 0, 0.0

        if in_pos:
            xp   = float(wk_raw["Close"].iloc[-1])
            xd   = wk_raw.index[-1]
            days = max((xd - ed).days, 1)
            gp   = (xp - ep) * qty_
            cst  = txn_costs(qty_, ep, xp)
            mti  = mtf_cost(ep, qty_, leverage, days, rate)
            np_  = gp - cst - mti
            cash_used = ep * qty_ / leverage
            trades.append(dict(
                symbol=sym, entry_date=ed, exit_date=xd,
                entry_price=round(ep, 2), exit_price=round(xp, 2),
                qty=qty_, holding_days=days, exit_reason="OPEN",
                gross_pnl=round(gp, 2), costs=round(cst, 2),
                mtf_interest=round(mti, 2), net_pnl=round(np_, 2),
                return_pct=round(np_ / cash_used * 100, 2),
                status="OPEN (MTM)",
            ))

    prog.empty()
    stat.empty()
    return pd.DataFrame(trades), failed, signals

# ─────────────────────────────────────────────────────────────
# GOOGLE SHEETS — N200 "Ready for Ranking" signal audit log
# Same spreadsheet n200_macd.py writes its live scans to, so backtest
# history and live signals live side by side.
# ─────────────────────────────────────────────────────────────

N200_CREDS_PATH  = r'/Users/gagankumarchavan/Documents/API Cred/noble-aquifer-437514-k4-a50658fe7247.json'
N200_SHEET_NAME  = "Momentum Watch list - Harish"
N200_SIGNAL_TAB  = "N200 Backtest Signals"


def log_signals_to_sheet(signals: list):
    """Append every Stage-1+Stage-2 signal from a backtest run to a
    dedicated audit-log tab. Returns (rows_written, error_message)."""
    if not signals:
        return 0, None
    try:
        scope = ["https://spreadsheets.google.com/feeds",
                 "https://www.googleapis.com/auth/drive"]
        creds  = Credentials.from_service_account_file(N200_CREDS_PATH, scopes=scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open(N200_SHEET_NAME)

        existing_ws = [ws.title for ws in spreadsheet.worksheets()]
        if N200_SIGNAL_TAB not in existing_ws:
            spreadsheet.add_worksheet(title=N200_SIGNAL_TAB, rows=200, cols=10)
        sheet = spreadsheet.worksheet(N200_SIGNAL_TAB)

        header = ["Symbol", "Week", "Monthly MACD", "Monthly Signal",
                  "Monthly ROC", "% from ATH", "Weekly MACD", "Weekly Signal"]
        if sheet.row_values(1) != header:
            sheet.update(range_name="A1", values=[header])

        rows = [[
            s["symbol"], s["week"].date().isoformat(), s["monthly_macd"],
            s["monthly_signal"], s["monthly_roc"], s["pct_from_ath"],
            s["weekly_macd"], s["weekly_signal"],
        ] for s in signals]

        chunk = 500
        for i in range(0, len(rows), chunk):
            sheet.append_rows(rows[i:i + chunk], value_input_option="USER_ENTERED")
        return len(rows), None
    except Exception as e:
        return 0, str(e)

# ─────────────────────────────────────────────────────────────
# EQUITY CURVE  (daily, using business-day calendar)
# ─────────────────────────────────────────────────────────────

def build_equity_curve(trades_df: pd.DataFrame, total_capital: float) -> pd.Series:
    if trades_df.empty:
        return pd.Series(dtype=float)
    t = trades_df.sort_values("exit_date")
    start = t["entry_date"].min()
    end   = t["exit_date"].max()
    dates = pd.bdate_range(start, end)
    daily_pnl = t.groupby("exit_date")["net_pnl"].sum().reindex(dates, fill_value=0.0)
    return (total_capital + daily_pnl.cumsum()).ffill()

# ─────────────────────────────────────────────────────────────
# PERFORMANCE METRICS
# ─────────────────────────────────────────────────────────────

def compute_metrics(trades_df: pd.DataFrame,
                    equity: pd.Series, total_capital: float) -> dict:
    if trades_df.empty or equity.empty:
        return {}

    wins   = trades_df[trades_df["net_pnl"] > 0]
    losses = trades_df[trades_df["net_pnl"] <= 0]
    loss_sum = losses["net_pnl"].sum()

    roll_max = equity.cummax()
    drawdown = (equity - roll_max) / roll_max * 100

    years    = max((equity.index[-1] - equity.index[0]).days / 365.25, 0.01)
    cagr     = ((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1) * 100

    dr       = equity.pct_change().dropna()
    ann_ret  = (1 + dr.mean()) ** 252 - 1
    ann_std  = dr.std() * np.sqrt(252)
    sharpe   = (ann_ret - RISK_FREE_RATE) / ann_std if ann_std > 0 else 0.0
    d_std    = dr[dr < 0].std() * np.sqrt(252)
    sortino  = (ann_ret - RISK_FREE_RATE) / d_std if d_std > 0 else 0.0

    # % of trading days the strategy had at least one open position
    all_dates   = pd.bdate_range(equity.index[0], equity.index[-1])
    open_flags  = pd.Series(False, index=all_dates)
    for _, row in trades_df.iterrows():
        mask = (all_dates >= row["entry_date"]) & (all_dates <= row["exit_date"])
        open_flags |= mask
    pct_in_market = open_flags.sum() / len(open_flags) * 100

    return {
        "num_trades":       len(trades_df),
        "total_net_pnl":    trades_df["net_pnl"].sum(),
        "total_gross_pnl":  trades_df["gross_pnl"].sum(),
        "total_costs":      trades_df["costs"].sum(),
        "total_mti":        trades_df["mtf_interest"].sum(),
        "total_return_pct": (equity.iloc[-1] / total_capital - 1) * 100,
        "cagr":             cagr,
        "max_drawdown":     drawdown.min(),
        "win_rate":         len(wins) / len(trades_df) * 100,
        "profit_factor":    abs(wins["net_pnl"].sum() / loss_sum)
                            if loss_sum != 0 else float("inf"),
        "sharpe":           sharpe,
        "sortino":          sortino,
        "avg_win":          wins["net_pnl"].mean()   if not wins.empty else 0,
        "avg_loss":         losses["net_pnl"].mean() if not losses.empty else 0,
        "best_trade":       trades_df["net_pnl"].max(),
        "worst_trade":      trades_df["net_pnl"].min(),
        "avg_hold":         trades_df["holding_days"].mean(),
        "open_positions":   (trades_df["status"] == "OPEN (MTM)").sum(),
        "pct_in_market":    pct_in_market,
    }

# ─────────────────────────────────────────────────────────────
# BUY-AND-HOLD BENCHMARK  (equal-weighted, same symbols)
# ─────────────────────────────────────────────────────────────

def buy_and_hold_series(sym_dict: dict, interval: str, start_date=None):
    """
    Equal-weighted buy-and-hold normalized to 1.0 at start_date.
    Each stock is normalized from start_date (or its own first date if no data
    at start_date). Stocks with no data in the period are skipped.
    Uses mean of available stocks per day (no dropna) to avoid losing history
    when some stocks have shorter listing history.
    """
    normals = []
    for _, ticker in sym_dict.items():
        df = fetch_data(ticker, interval)
        if df is None or df.empty:
            continue
        close = df["Close"].dropna()
        # Clip to start_date so normalization base = start of backtest period
        if start_date is not None:
            close = close[close.index >= pd.Timestamp(start_date)]
        if len(close) < 2:
            continue
        normals.append(close / close.iloc[0])   # normalized to 1.0 at start_date
    if not normals:
        return None
    # mean(axis=1) ignores NaN per row — handles stocks with different listing dates
    aligned = pd.concat(normals, axis=1)
    return aligned.mean(axis=1)

# ─────────────────────────────────────────────────────────────
# CHARTS
# ─────────────────────────────────────────────────────────────

def equity_chart(equity: pd.Series, nifty50,
                 bnh, title: str) -> go.Figure:
    fig  = go.Figure()
    base = equity.iloc[0]

    fig.add_trace(go.Scatter(
        x=equity.index, y=(equity / base * 100),
        name="Strategy", line=dict(color="#00C9A7", width=2.5),
    ))

    if nifty50 is not None:
        n = nifty50["Close"].dropna()
        n = n[(n.index >= equity.index[0]) & (n.index <= equity.index[-1])]
        if not n.empty:
            fig.add_trace(go.Scatter(
                x=n.index, y=(n / n.iloc[0] * 100),
                name="Nifty 50", line=dict(color="#FF6B6B", width=1.5, dash="dot"),
            ))

    if bnh is not None:
        bnh_clip = bnh[(bnh.index >= equity.index[0]) & (bnh.index <= equity.index[-1])]
        bnh_clip = bnh_clip.dropna()
        if not bnh_clip.empty and bnh_clip.iloc[0] != 0:
            fig.add_trace(go.Scatter(
                x=bnh_clip.index, y=(bnh_clip / bnh_clip.iloc[0] * 100),
                name="Buy & Hold (same symbols)",
                line=dict(color="#FFA500", width=1.5, dash="dash"),
            ))

    fig.update_layout(
        title=title, height=430,
        xaxis_title="Date", yaxis_title="Normalized Value (Start = 100)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def market_exposure_chart(trades_df: pd.DataFrame,
                           equity: pd.Series) -> go.Figure:
    """
    Bar chart: one bar per business day.
    Green  = deployed (≥1 position open that day).
    Grey   = idle (no open position).
    """
    dates  = pd.bdate_range(equity.index[0], equity.index[-1])
    counts = pd.Series(0, index=dates, dtype=int)
    for _, row in trades_df.iterrows():
        mask = (dates >= row["entry_date"]) & (dates <= row["exit_date"])
        counts[mask] += 1

    pct    = counts[counts > 0].count() / len(counts) * 100
    colors = ["#00C9A7" if v > 0 else "#d0d0d0" for v in counts]

    fig = go.Figure(go.Bar(
        x=counts.index, y=counts.values,
        marker_color=colors, name="Open Positions",
        hovertemplate="%{x|%Y-%m-%d}<br>%{y} position(s) open<extra></extra>",
    ))
    fig.update_layout(
        title=f"Deployed vs Idle  —  Strategy in-market {pct:.1f}% of trading days  "
              f"(green = deployed, grey = idle)",
        height=230,
        xaxis_title="Date", yaxis_title="# Open Positions",
        hovermode="x unified", showlegend=False, bargap=0,
    )
    return fig


def deployment_timeline_chart(trades_df: pd.DataFrame, title: str) -> go.Figure:
    """
    Gantt chart: one row per symbol.
    Green bar = profitable trade, Red bar = losing trade.
    Gaps between bars = idle (no position in that symbol).
    """
    df = trades_df.copy()
    df["outcome"] = df["net_pnl"].apply(lambda x: "Profit" if x >= 0 else "Loss")
    df["hover"]   = df.apply(
        lambda r: (f"{r['symbol']}  |  "
                   f"{r['entry_date'].date()} → {r['exit_date'].date()}  |  "
                   f"{r['holding_days']}d  |  "
                   f"₹{r['net_pnl']:,.0f}  ({r['return_pct']:.1f}%)"),
        axis=1,
    )
    fig = px.timeline(
        df.sort_values(["symbol", "entry_date"]),
        x_start="entry_date", x_end="exit_date", y="symbol",
        color="outcome",
        color_discrete_map={"Profit": "#00C9A7", "Loss": "#FF6B6B"},
        hover_name="hover",
        title=title,
    )
    fig.update_yaxes(autorange="reversed")
    n_syms = df["symbol"].nunique()
    fig.update_layout(
        height=max(450, n_syms * 26 + 150),
        legend_title_text="Trade Outcome",
        xaxis_title="Date", yaxis_title="Symbol",
    )
    return fig


def pnl_dist_chart(trades_df: pd.DataFrame) -> go.Figure:
    colors = ["#00C9A7" if v >= 0 else "#FF6B6B" for v in trades_df["net_pnl"]]
    fig = go.Figure(go.Histogram(
        x=trades_df["net_pnl"], nbinsx=30, marker_color=colors,
    ))
    fig.update_layout(
        title="Net P&L Distribution per Trade",
        xaxis_title="Net P&L (₹)", yaxis_title="# Trades", height=320,
    )
    return fig


def per_symbol_chart(trades_df: pd.DataFrame) -> go.Figure:
    s = (trades_df.groupby("symbol")["net_pnl"]
         .sum().sort_values(ascending=True))
    colors = ["#00C9A7" if v >= 0 else "#FF6B6B" for v in s]
    fig = go.Figure(go.Bar(
        x=s.values, y=s.index, orientation="h",
        marker_color=colors,
        text=[f"₹{v:,.0f}" for v in s.values], textposition="outside",
    ))
    fig.update_layout(
        title="Net P&L by Symbol",
        height=max(320, len(s) * 28), xaxis_title="Net P&L (₹)",
    )
    return fig


def drawdown_chart(equity: pd.Series) -> go.Figure:
    roll_max = equity.cummax()
    dd = (equity - roll_max) / roll_max * 100
    fig = go.Figure(go.Scatter(
        x=dd.index, y=dd.values,
        fill="tozeroy", line=dict(color="#FF6B6B", width=1),
        fillcolor="rgba(255,107,107,0.3)", name="Drawdown",
    ))
    fig.update_layout(
        title="Drawdown (%)", height=250,
        xaxis_title="Date", yaxis_title="Drawdown %", hovermode="x unified",
    )
    return fig

# ─────────────────────────────────────────────────────────────
# METRIC CARDS  (shared UI component)
# ─────────────────────────────────────────────────────────────

def show_metrics(m: dict, label: str = ""):
    if not m:
        return
    st.markdown(f"### {label} — Performance Summary")

    if m.get("open_positions", 0) > 0:
        st.info(
            f"ℹ️  {m['open_positions']} position(s) still open — "
            "marked to market at last available close. "
            "Costs & MTF interest included up to that date."
        )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Net P&L",      f"₹{m['total_net_pnl']:,.0f}",
              f"{m['total_return_pct']:.1f}% total return")
    c2.metric("CAGR",         f"{m['cagr']:.1f}%")
    c3.metric("Max Drawdown", f"{m['max_drawdown']:.1f}%")
    c4.metric("Win Rate",     f"{m['win_rate']:.1f}%",
              f"{m['num_trades']} trades")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Profit Factor",   f"{m['profit_factor']:.2f}")
    c6.metric("Sharpe Ratio",    f"{m['sharpe']:.2f}")
    c7.metric("Sortino Ratio",   f"{m['sortino']:.2f}")
    c8.metric("% Time in Market",
              f"{m.get('pct_in_market', 0):.1f}%",
              f"Avg hold {m['avg_hold']:.0f}d")

    with st.expander("🔍 Detailed Cost & Trade Breakdown"):
        d1, d2, d3 = st.columns(3)
        d1.metric("Gross P&L",          f"₹{m['total_gross_pnl']:,.0f}")
        d2.metric("Transaction Costs",  f"₹{m['total_costs']:,.0f}")
        d3.metric("MTF Interest Paid",  f"₹{m['total_mti']:,.0f}")

        d4, d5, d6 = st.columns(3)
        d4.metric("Avg Winning Trade",  f"₹{m['avg_win']:,.0f}")
        d5.metric("Avg Losing Trade",   f"₹{m['avg_loss']:,.0f}")
        d6.metric("Best / Worst Trade",
                  f"₹{m['best_trade']:,.0f} / ₹{m['worst_trade']:,.0f}")

# ─────────────────────────────────────────────────────────────
# TRADE LOG DISPLAY
# ─────────────────────────────────────────────────────────────

def show_trade_log(trades_df: pd.DataFrame, filename: str):
    st.subheader("📋 Trade Log")

    preferred = ["symbol", "entry_date", "exit_date", "entry_price",
                 "exit_price", "qty", "holding_days", "exit_reason",
                 "gross_pnl", "costs", "mtf_interest", "net_pnl",
                 "return_pct", "status"]
    cols = [c for c in preferred if c in trades_df.columns]

    def color_pnl(val):
        if isinstance(val, (int, float)):
            return "color: #00C9A7" if val > 0 else "color: #FF6B6B"
        return ""

    styled = (
        trades_df[cols]
        .sort_values("entry_date", ascending=False)
        .style.map(color_pnl, subset=["net_pnl"])
    )
    st.dataframe(styled, use_container_width=True, height=420)

    csv = trades_df.to_csv(index=False)
    st.download_button("⬇️ Download Trade Log (CSV)", csv, filename, "text/csv")

# ─────────────────────────────────────────────────────────────
# CONFIG PANEL  (shared layout helper)
# ─────────────────────────────────────────────────────────────

def config_panel(key_prefix: str, universe: dict,
                 default_fast: int, default_slow: int, default_sig: int,
                 has_target: bool = False):
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        selected = st.multiselect(
            "Select symbols", options=list(universe.keys()),
            default=list(universe.keys()),
            key=f"{key_prefix}_symbols",
        )
        dcol1, dcol2 = st.columns(2)
        with dcol1:
            from datetime import date as date_type
            start_date = st.date_input(
                "Backtest from",
                value=date_type(2015, 1, 1),
                min_value=date_type(2000, 1, 1),
                max_value=date_type.today(),
                key=f"{key_prefix}_start",
                help="Symbols with no data before this date will start from their listing date"
            )
        with dcol2:
            end_date = st.date_input(
                "Backtest to",
                value=date_type.today(),
                min_value=date_type(2000, 1, 1),
                max_value=date_type.today(),
                key=f"{key_prefix}_end",
            )

    with col2:
        fast   = st.number_input("MACD Fast",   value=default_fast,
                                  min_value=2, max_value=50,  key=f"{key_prefix}_fast")
        slow   = st.number_input("MACD Slow",   value=default_slow,
                                  min_value=5, max_value=200, key=f"{key_prefix}_slow")
        signal = st.number_input("MACD Signal", value=default_sig,
                                  min_value=2, max_value=50,  key=f"{key_prefix}_sig")

    with col3:
        cash     = st.number_input("Cash per symbol (₹)", value=10000, step=1000,
                                    key=f"{key_prefix}_cash")
        leverage = st.selectbox(
            "Leverage", [1, 2, 3, 4, 5], index=3,
            format_func=lambda x: f"{x}x  ({'CNC' if x == 1 else 'MTF'})",
            key=f"{key_prefix}_lev",
        )
        rate     = st.number_input("MTF rate (% p.a.)", value=14.0,
                                    min_value=0.0, max_value=30.0, step=0.5,
                                    key=f"{key_prefix}_rate") / 100
        target   = None
        if has_target:
            target = st.number_input("Target exit (%)", value=3.5,
                                      min_value=0.5, max_value=50.0, step=0.5,
                                      key=f"{key_prefix}_target") / 100

    run = st.button("🚀 Run Backtest", type="primary",
                    use_container_width=True, key=f"{key_prefix}_run")

    return (selected, int(fast), int(slow), int(signal),
            cash, int(leverage), rate, target, run,
            pd.Timestamp(start_date), pd.Timestamp(end_date))

# ─────────────────────────────────────────────────────────────
# ENTRY / EXIT CRITERIA PANEL  (shared UI component)
# ─────────────────────────────────────────────────────────────

def criteria_panel(key_prefix: str, htf_label: str,
                   has_target: bool = False, default_target: float = 0.0) -> dict:
    """
    Configurable entry & exit rules expander.
    Returns a dict with all rule settings to pass into the backtest engine.
    """
    with st.expander("🎯 Entry & Exit Rules", expanded=False):
        ec, xc = st.columns(2)

        with ec:
            st.markdown("**Entry Criteria**")
            use_htf = st.checkbox(
                f"Require {htf_label} MACD > Signal (trend filter)",
                value=True, key=f"{key_prefix}_use_htf",
                help="OFF = skip the higher-timeframe filter. More trades but more whipsaws.",
            )
            entry_trig = st.selectbox(
                "Entry trigger", key=f"{key_prefix}_entry_trig",
                options=["crossover", "above_signal", "above_zero"],
                format_func=lambda x: {
                    "crossover":    "MACD crosses above Signal ↑  (default)",
                    "above_signal": "MACD already > Signal  (no crossover needed)",
                    "above_zero":   "MACD crosses above Zero line",
                }[x],
                help="crossover = strictest (current candle flips above). "
                     "above_signal = enter anytime MACD is above signal (more trades). "
                     "above_zero = only enter when MACD itself turns positive.",
            )
            sma_period = st.selectbox(
                "Additional SMA price filter", key=f"{key_prefix}_sma",
                options=[0, 10, 20, 50],
                format_func=lambda x: "Off" if x == 0 else f"Close must be above SMA({x})",
                help="Extra confirmation: only enter if price is above its N-period moving average.",
            )

        with xc:
            st.markdown("**Exit Criteria**")
            exit_trig = st.selectbox(
                "Exit trigger", key=f"{key_prefix}_exit_trig",
                options=["crossover", "below_signal", "below_zero"],
                format_func=lambda x: {
                    "crossover":    "MACD crosses below Signal ↓  (default)",
                    "below_signal": "MACD already < Signal  (no crossover needed)",
                    "below_zero":   "MACD crosses below Zero line  (stay longer)",
                }[x],
                help="crossover = exit when MACD dips below signal. "
                     "below_signal = exit the moment MACD < signal (earlier). "
                     "below_zero = stay in until MACD turns negative (rides trend longer).",
            )
            stop_loss = st.number_input(
                "Stop Loss % from entry  (0 = off)", value=0.0,
                min_value=0.0, max_value=50.0, step=0.5,
                key=f"{key_prefix}_sl",
                help="Hard stop: exit next open if close drops this % below entry price.",
            ) / 100
            trailing_stop = st.number_input(
                "Trailing Stop % from peak  (0 = off)", value=0.0,
                min_value=0.0, max_value=30.0, step=0.5,
                key=f"{key_prefix}_trail",
                help="Exit next open if close drops this % from the highest close since entry.",
            ) / 100
            target_pct = 0.0
            if has_target:
                target_pct = st.number_input(
                    "Target % from entry  (0 = off)", value=default_target * 100,
                    min_value=0.0, max_value=100.0, step=0.5,
                    key=f"{key_prefix}_tgt",
                    help="Take profit: exit next open if close hits this % above entry.",
                ) / 100

    rules = dict(
        use_htf_filter=use_htf,
        entry_trigger=entry_trig,
        exit_trigger=exit_trig,
        sma_period=int(sma_period),
        stop_loss_pct=stop_loss,
        trailing_stop_pct=trailing_stop,
    )
    if has_target:
        rules["target_pct"] = target_pct
    return rules


EXIT_REASON_LABELS = {
    "MACD_EXIT":  "MACD Exit",
    "TARGET":     "Target Hit",
    "STOP_LOSS":  "Stop Loss",
    "TRAIL_STOP": "Trailing Stop",
    "ATR_STOP":   "ATR Stop",
    "ATR_TRAIL":  "ATR Trailing Stop",
    "PREV_LOW_BREAK": "Prev-Day Low Break",
    "TIME_EXIT":  "Time Cap",
    "RSI_EXIT":   "RSI Reversal",
    "OPEN":       "Still Open (MTM)",
}


def exit_reason_breakdown(tdf: pd.DataFrame):
    """Show a breakdown of why trades exited."""
    if "exit_reason" not in tdf.columns:
        return
    st.subheader("Exit Reason Breakdown")
    rc = tdf["exit_reason"].value_counts()
    cols = st.columns(len(rc))
    for col, key in zip(cols, rc.index):
        col.metric(EXIT_REASON_LABELS.get(key, key), int(rc[key]))


# ─────────────────────────────────────────────────────────────
# MAIN TABS
# ─────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs(
    ["📊 ETF Strategy", "📈 Nifty 100 Strategy", "🎯 Nifty 500 Momentum Screener",
     "🕯️ N200 Heikin-Ashi MACD"]
)

# ════════════════════════════════════════════════════════════
# TAB 1 — ETF STRATEGY
# ════════════════════════════════════════════════════════════

with tab1:
    st.subheader("ETF Strategy — Monthly MACD Filter + Weekly Crossover")
    st.caption(
        "Entry: Monthly MACD > Signal  **AND**  Weekly MACD crosses above Signal  →  "
        "enter next Monday open  |  "
        "Exit: Weekly MACD crosses below Signal  →  exit next Monday open"
    )

    with st.expander("⚙️ Configure & Run", expanded=True):
        (e_syms, e_fast, e_slow, e_sig,
         e_cash, e_lev, e_rate, _, e_run,
         e_start, e_end) = config_panel(
            "etf", ALL_ETFS, 12, 24, 3, has_target=False
        )

    e_rules = criteria_panel("etf", htf_label="Monthly", has_target=True, default_target=0.0)

    if e_run:
        if not e_syms:
            st.error("Select at least one ETF.")
        else:
            sel_etfs  = {k: ALL_ETFS[k] for k in e_syms}
            total_cap = e_cash * len(sel_etfs)

            st.info(
                f"Running on **{len(sel_etfs)} ETFs** | "
                f"₹{e_cash:,} × {e_lev}x = ₹{e_cash * e_lev:,} per ETF | "
                f"Total capital: ₹{total_cap:,} | "
                f"Period: **{e_start.date()} → {e_end.date()}**"
            )

            with st.spinner("Fetching data & running backtest..."):
                tdf, failed = run_etf_backtest(
                    sel_etfs, e_fast, e_slow, e_sig, e_cash, e_lev, e_rate,
                    start_date=e_start, end_date=e_end,
                    **e_rules,
                )

            if tdf.empty:
                st.error("No trades generated. Try adjusting MACD parameters or date range.")
            else:
                equity  = build_equity_curve(tdf, total_cap)
                metrics = compute_metrics(tdf, equity, total_cap)
                st.session_state["etf_results"] = dict(
                    tdf=tdf, equity=equity, metrics=metrics, failed=failed,
                    total_cap=total_cap, sel_etfs=sel_etfs,
                    e_start=e_start, e_end=e_end,
                    e_fast=e_fast, e_slow=e_slow, e_sig=e_sig,
                )

    if "etf_results" in st.session_state:
        r         = st.session_state["etf_results"]
        tdf       = r["tdf"]
        equity    = r["equity"]
        metrics   = r["metrics"]
        failed    = r["failed"]
        total_cap = r["total_cap"]
        sel_etfs  = r["sel_etfs"]
        e_start_r = r["e_start"]
        e_end_r   = r["e_end"]
        e_fast_r  = r["e_fast"]
        e_slow_r  = r["e_slow"]
        e_sig_r   = r["e_sig"]

        # n50 and bnh are @st.cache_data — fast to recompute, no need to store in state
        n50 = fetch_nifty50()
        bnh = buy_and_hold_series(sel_etfs, "1wk", start_date=equity.index[0])

        if failed:
            st.warning(f"⚠️ No data for: {', '.join(failed)}")

        first_trade  = tdf["entry_date"].min().date()
        last_trade   = tdf["exit_date"].max().date()
        years_tested = (tdf["exit_date"].max() - tdf["entry_date"].min()).days / 365.25
        warmup_days  = (tdf["entry_date"].min() - e_start_r).days
        st.success(
            f"📅 **Configured:** {e_start_r.date()} → {e_end_r.date()}  |  "
            f"**First actual trade:** {first_trade}  |  "
            f"**Last actual trade:** {last_trade}  ({years_tested:.1f} years)"
        )
        if warmup_days > 30:
            st.caption(
                f"ℹ️ Start shifted by ~{warmup_days} days: MACD({e_fast_r},{e_slow_r},{e_sig_r}) "
                f"on weekly data needs {e_slow_r + e_sig_r + 2} candles (~"
                f"{(e_slow_r + e_sig_r + 2) // 4} months) of warmup before the first "
                "signal can fire. End date reflects last available data / last exit signal."
            )

        with st.expander("📊 Per-symbol data range"):
            sym_summary = (
                tdf.groupby("symbol")
                .agg(first_trade=("entry_date", "min"),
                     last_trade=("exit_date", "max"),
                     num_trades=("net_pnl", "count"),
                     net_pnl=("net_pnl", "sum"))
                .reset_index()
                .sort_values("first_trade")
            )
            sym_summary["first_trade"] = sym_summary["first_trade"].dt.date
            sym_summary["last_trade"]  = sym_summary["last_trade"].dt.date
            sym_summary["net_pnl"]     = sym_summary["net_pnl"].map("₹{:,.0f}".format)
            st.dataframe(sym_summary, use_container_width=True)

        show_metrics(metrics, "ETF Strategy")
        st.plotly_chart(
            equity_chart(equity, n50, bnh,
                         "ETF Strategy — Equity Curve vs Benchmarks"),
            use_container_width=True,
        )
        st.plotly_chart(drawdown_chart(equity), use_container_width=True)

        st.plotly_chart(
            market_exposure_chart(tdf, equity),
            use_container_width=True,
        )

        with st.expander("📅 Strategy Deployment Timeline (per ETF)"):
            st.caption(
                "Green = profitable trade in progress | "
                "Red = losing trade in progress | "
                "Gap = idle (no position)"
            )
            st.plotly_chart(
                deployment_timeline_chart(
                    tdf, "ETF Strategy — Deployed vs Idle Periods per Symbol"
                ),
                use_container_width=True,
            )

        ca, cb = st.columns(2)
        with ca:
            st.plotly_chart(pnl_dist_chart(tdf), use_container_width=True)
        with cb:
            st.plotly_chart(per_symbol_chart(tdf), use_container_width=True)

        exit_reason_breakdown(tdf)
        show_trade_log(tdf, "etf_backtest_trades.csv")

# ════════════════════════════════════════════════════════════
# TAB 2 — NIFTY 100 STRATEGY
# ════════════════════════════════════════════════════════════

with tab2:
    st.subheader("Nifty 100 Strategy — Weekly MACD Filter + Daily Crossover + Target Exit")
    st.caption(
        "Entry: Weekly MACD > Signal  **AND**  Daily MACD crosses above Signal  →  "
        "enter next day open  |  "
        "Exit: Daily MACD crosses below Signal  **OR**  Target hit  →  exit next day open"
    )

    with st.expander("⚙️ Configure & Run", expanded=True):
        (n_syms, n_fast, n_slow, n_sig,
         n_cash, n_lev, n_rate, n_target, n_run,
         n_start, n_end) = config_panel(
            "n100", NIFTY100_STOCKS, 12, 24, 3, has_target=True
        )

    n_rules = criteria_panel("n100", htf_label="Weekly", has_target=False)

    if n_run:
        if not n_syms:
            st.error("Select at least one stock.")
        else:
            sel_stocks = {k: NIFTY100_STOCKS[k] for k in n_syms}
            total_cap  = n_cash * len(sel_stocks)

            st.info(
                f"Running on **{len(sel_stocks)} stocks** | "
                f"₹{n_cash:,} × {n_lev}x = ₹{n_cash * n_lev:,} per stock | "
                f"Total capital: ₹{total_cap:,} | "
                f"Target: {n_target*100:.1f}% | "
                f"Period: **{n_start.date()} → {n_end.date()}**"
            )
            if len(sel_stocks) > 30:
                st.warning(
                    f"Fetching {len(sel_stocks)} stocks takes 2–4 minutes. "
                    "Data is cached — subsequent runs with different MACD params are instant."
                )

            with st.spinner("Fetching data & running backtest..."):
                tdf, failed = run_nifty100_backtest(
                    sel_stocks, n_fast, n_slow, n_sig,
                    n_cash, n_lev, n_rate, n_target,
                    start_date=n_start, end_date=n_end,
                    **n_rules,
                )

            if tdf.empty:
                st.error("No trades generated. Try adjusting MACD parameters or date range.")
            else:
                equity  = build_equity_curve(tdf, total_cap)
                metrics = compute_metrics(tdf, equity, total_cap)
                st.session_state["n100_results"] = dict(
                    tdf=tdf, equity=equity, metrics=metrics, failed=failed,
                    total_cap=total_cap, sel_stocks=sel_stocks,
                    n_start=n_start, n_end=n_end,
                    n_fast=n_fast, n_slow=n_slow, n_sig=n_sig,
                )

    if "n100_results" in st.session_state:
        r         = st.session_state["n100_results"]
        tdf       = r["tdf"]
        equity    = r["equity"]
        metrics   = r["metrics"]
        failed    = r["failed"]
        total_cap = r["total_cap"]
        sel_stocks = r["sel_stocks"]
        n_start_r  = r["n_start"]
        n_end_r    = r["n_end"]
        n_fast_r   = r["n_fast"]
        n_slow_r   = r["n_slow"]
        n_sig_r    = r["n_sig"]

        n50 = fetch_nifty50()
        bnh = buy_and_hold_series(sel_stocks, "1d", start_date=equity.index[0])

        if failed:
            st.warning(f"⚠️ No data for: {', '.join(failed)}")

        first_trade  = tdf["entry_date"].min().date()
        last_trade   = tdf["exit_date"].max().date()
        years_tested = (tdf["exit_date"].max() - tdf["entry_date"].min()).days / 365.25
        warmup_days  = (tdf["entry_date"].min() - n_start_r).days
        st.success(
            f"📅 **Configured:** {n_start_r.date()} → {n_end_r.date()}  |  "
            f"**First actual trade:** {first_trade}  |  "
            f"**Last actual trade:** {last_trade}  ({years_tested:.1f} years)"
        )
        if warmup_days > 30:
            st.caption(
                f"ℹ️ Start shifted by ~{warmup_days} days: MACD({n_fast_r},{n_slow_r},{n_sig_r}) "
                f"on daily data needs {n_slow_r + n_sig_r + 2} candles (~"
                f"{(n_slow_r + n_sig_r + 2) // 21} months) of warmup before the first "
                "signal can fire. End date reflects last available data / last exit signal."
            )

        with st.expander("📊 Per-symbol data range"):
            sym_summary = (
                tdf.groupby("symbol")
                .agg(first_trade=("entry_date", "min"),
                     last_trade=("exit_date", "max"),
                     num_trades=("net_pnl", "count"),
                     net_pnl=("net_pnl", "sum"))
                .reset_index()
                .sort_values("first_trade")
            )
            sym_summary["first_trade"] = sym_summary["first_trade"].dt.date
            sym_summary["last_trade"]  = sym_summary["last_trade"].dt.date
            sym_summary["net_pnl"]     = sym_summary["net_pnl"].map("₹{:,.0f}".format)
            st.dataframe(sym_summary, use_container_width=True)

        show_metrics(metrics, "Nifty 100 Strategy")
        st.plotly_chart(
            equity_chart(equity, n50, bnh,
                         "Nifty 100 Strategy — Equity Curve vs Benchmarks"),
            use_container_width=True,
        )
        st.plotly_chart(drawdown_chart(equity), use_container_width=True)

        st.plotly_chart(
            market_exposure_chart(tdf, equity),
            use_container_width=True,
        )

        with st.expander("📅 Strategy Deployment Timeline (per stock)"):
            st.caption(
                "Green = profitable trade in progress | "
                "Red = losing trade in progress | "
                "Gap = idle (no position)"
            )
            st.plotly_chart(
                deployment_timeline_chart(
                    tdf, "Nifty 100 Strategy — Deployed vs Idle Periods per Symbol"
                ),
                use_container_width=True,
            )

        ca, cb = st.columns(2)
        with ca:
            st.plotly_chart(pnl_dist_chart(tdf), use_container_width=True)
        with cb:
            st.plotly_chart(per_symbol_chart(tdf), use_container_width=True)

        exit_reason_breakdown(tdf)
        show_trade_log(tdf, "nifty100_backtest_trades.csv")

# ════════════════════════════════════════════════════════════
# TAB 3 — NIFTY 500 MOMENTUM SCREENER STRATEGY
# ════════════════════════════════════════════════════════════

with tab3:
    st.subheader("Nifty 500 Momentum Screener — RSI + Williams %R + CCI")
    st.caption(
        "Entry: Daily RSI crosses above level  **AND**  Williams %R crosses above level  "
        "**AND**  CCI(Daily High) crosses above level — all on the same day  →  "
        "enter next day's open  |  "
        "Exit: Target % / Stop-loss % / Trailing-stop % / Max holding days / "
        "optional RSI reversal  →  exit next day's open"
    )

    with st.expander("⚙️ Configure & Run", expanded=True):
        sc1, sc2, sc3 = st.columns([2, 1, 1])

        with sc1:
            s_syms = st.multiselect(
                "Select symbols", options=list(NIFTY500_STOCKS.keys()),
                default=list(NIFTY500_STOCKS.keys()), key="scr_symbols",
            )
            sdcol1, sdcol2 = st.columns(2)
            with sdcol1:
                from datetime import date as date_type
                s_start = st.date_input(
                    "Backtest from", value=date_type(2015, 1, 1),
                    min_value=date_type(2000, 1, 1), max_value=date_type.today(),
                    key="scr_start",
                    help="Symbols with no data before this date will start from their listing date",
                )
            with sdcol2:
                s_end = st.date_input(
                    "Backtest to", value=date_type.today(),
                    min_value=date_type(2000, 1, 1), max_value=date_type.today(),
                    key="scr_end",
                )

        with sc2:
            st.markdown("**RSI**")
            rsi_period = st.number_input("Period", value=14, min_value=2, max_value=100,
                                         key="scr_rsi_period")
            rsi_level  = st.number_input("Crossed-above level", value=65.0,
                                         min_value=1.0, max_value=99.0, step=1.0,
                                         key="scr_rsi_level")
            st.markdown("**Williams %R**")
            wr_period  = st.number_input("Period ", value=140, min_value=2, max_value=300,
                                         key="scr_wr_period")
            wr_level   = st.number_input("Crossed-above level ", value=-20.0,
                                         min_value=-99.0, max_value=-1.0, step=1.0,
                                         key="scr_wr_level")

        with sc3:
            st.markdown("**CCI (on Daily High)**")
            cci_period = st.number_input("Period  ", value=200, min_value=2, max_value=500,
                                         key="scr_cci_period")
            cci_level  = st.number_input("Crossed-above level  ", value=100.0,
                                         min_value=-300.0, max_value=300.0, step=5.0,
                                         key="scr_cci_level")
            s_cash = st.number_input("Cash per symbol (₹)", value=10000, step=1000,
                                     key="scr_cash")
            s_lev = st.selectbox(
                "Leverage", [1, 2, 3, 4, 5], index=0,
                format_func=lambda x: f"{x}x  ({'CNC' if x == 1 else 'MTF'})",
                key="scr_lev",
            )
            s_rate = st.number_input("MTF rate (% p.a.)", value=14.0,
                                     min_value=0.0, max_value=30.0, step=0.5,
                                     key="scr_rate") / 100

        s_run = st.button("🚀 Run Backtest", type="primary",
                          use_container_width=True, key="scr_run")

    with st.expander("🎯 Exit Rules", expanded=False):
        st.caption(
            "Entry is fixed by the screener (all three indicators must cross above "
            "their levels the same day — thresholds configurable above). "
            "Exit rules below are fully flexible — combine as many as you like; "
            "whichever triggers first closes the trade."
        )
        xc1, xc2 = st.columns(2)
        with xc1:
            target_pct = st.number_input(
                "Target % from entry  (0 = off)", value=5.0,
                min_value=0.0, max_value=100.0, step=0.5, key="scr_tgt",
            ) / 100
            stop_loss = st.number_input(
                "Stop Loss % from entry  (0 = off)", value=0.0,
                min_value=0.0, max_value=50.0, step=0.5, key="scr_sl",
            ) / 100
            trailing_stop = st.number_input(
                "Trailing Stop % from peak  (0 = off)", value=0.0,
                min_value=0.0, max_value=30.0, step=0.5, key="scr_trail",
            ) / 100
            use_prev_low_stop = st.checkbox(
                "Also exit if price breaks below previous day's low "
                "(only when target not yet hit)",
                value=False, key="scr_use_prev_low",
                help="Dynamic daily stop: if today's low breaks below yesterday's "
                     "low and the target hasn't fired, exit next day's open.",
            )
            use_atr_stop = st.checkbox(
                "Also exit on ATR-based stop  (entry − mult × ATR)",
                value=False, key="scr_use_atr",
                help="Volatility-adjusted stop: sizes the stop distance to each "
                     "stock's own average daily range instead of a flat %.",
            )
            atr_c1, atr_c2 = st.columns(2)
            with atr_c1:
                atr_period = st.number_input(
                    "ATR Period", value=14, min_value=2, max_value=100,
                    key="scr_atr_period", disabled=not use_atr_stop,
                )
            with atr_c2:
                atr_mult = st.number_input(
                    "ATR Multiplier", value=1.5, min_value=0.1, max_value=10.0,
                    step=0.1, key="scr_atr_mult", disabled=not use_atr_stop,
                )
        with xc2:
            max_hold = st.number_input(
                "Max Holding Days  (0 = off)", value=0,
                min_value=0, max_value=365, step=1, key="scr_maxhold",
            )
            use_rsi_exit = st.checkbox(
                "Also exit on RSI reversal (crosses back below level)",
                value=False, key="scr_use_rsi_exit",
            )
            rsi_exit_level = st.number_input(
                "RSI reversal exit level", value=50.0,
                min_value=1.0, max_value=99.0, step=1.0,
                key="scr_rsi_exit_level", disabled=not use_rsi_exit,
            )
            use_atr_trail = st.checkbox(
                "Also exit on ATR Trailing Stop  (peak − mult × ATR)",
                value=False, key="scr_use_atr_trail",
                help="Chandelier-style stop: trails up as price makes new highs, "
                     "sized to the stock's own volatility instead of a flat %. "
                     "Never moves down, only up — lets a real trend run while "
                     "still cutting losers.",
            )
            atrt_c1, atrt_c2 = st.columns(2)
            with atrt_c1:
                atr_trail_period = st.number_input(
                    "ATR Period ", value=14, min_value=2, max_value=100,
                    key="scr_atr_trail_period", disabled=not use_atr_trail,
                )
            with atrt_c2:
                atr_trail_mult = st.number_input(
                    "ATR Multiplier ", value=3.0, min_value=0.1, max_value=10.0,
                    step=0.1, key="scr_atr_trail_mult", disabled=not use_atr_trail,
                )
            use_macd_exit = st.checkbox(
                "Also exit on MACD bearish crossover",
                value=False, key="scr_use_macd_exit",
                help="Exit when the daily MACD line crosses below its signal "
                     "line — a momentum-reversal signal, independent of the "
                     "entry filter's RSI/Williams %R/CCI.",
            )
            macd_c1, macd_c2, macd_c3 = st.columns(3)
            with macd_c1:
                macd_fast = st.number_input(
                    "MACD Fast", value=12, min_value=2, max_value=50,
                    key="scr_macd_fast", disabled=not use_macd_exit,
                )
            with macd_c2:
                macd_slow = st.number_input(
                    "MACD Slow", value=24, min_value=5, max_value=200,
                    key="scr_macd_slow", disabled=not use_macd_exit,
                )
            with macd_c3:
                macd_sig = st.number_input(
                    "MACD Signal", value=6, min_value=2, max_value=50,
                    key="scr_macd_sig", disabled=not use_macd_exit,
                )

    if s_run:
        if not s_syms:
            st.error("Select at least one stock.")
        elif target_pct == 0 and stop_loss == 0 and trailing_stop == 0 \
                and max_hold == 0 and not use_rsi_exit and not use_prev_low_stop \
                and not use_atr_stop and not use_atr_trail and not use_macd_exit:
            st.error("Select at least one exit rule (target / stop / trailing / "
                     "ATR stop / ATR trail / MACD reversal / prev-day low / "
                     "time cap / RSI reversal).")
        else:
            sel_stocks = {k: NIFTY500_STOCKS[k] for k in s_syms}
            total_cap  = s_cash * len(sel_stocks)

            st.info(
                f"Running on **{len(sel_stocks)} stocks** | "
                f"₹{s_cash:,} × {s_lev}x = ₹{s_cash * s_lev:,} per stock | "
                f"Total capital: ₹{total_cap:,} | "
                f"Period: **{s_start} → {s_end}**"
            )
            if len(sel_stocks) > 50:
                st.warning(
                    f"Fetching {len(sel_stocks)} stocks can take several minutes on "
                    "the first run. Data is cached — subsequent runs with different "
                    "parameters are instant."
                )

            with st.spinner("Fetching data & running backtest..."):
                tdf, failed = run_screener_backtest(
                    sel_stocks, int(rsi_period), rsi_level, int(wr_period), wr_level,
                    int(cci_period), cci_level, s_cash, int(s_lev), s_rate,
                    start_date=pd.Timestamp(s_start), end_date=pd.Timestamp(s_end),
                    target_pct=target_pct, stop_loss_pct=stop_loss,
                    trailing_stop_pct=trailing_stop, max_hold_days=int(max_hold),
                    use_rsi_exit=use_rsi_exit, rsi_exit_level=rsi_exit_level,
                    use_prev_low_stop=use_prev_low_stop,
                    use_atr_stop=use_atr_stop, atr_period=int(atr_period),
                    atr_mult=atr_mult,
                    use_atr_trail=use_atr_trail, atr_trail_period=int(atr_trail_period),
                    atr_trail_mult=atr_trail_mult,
                    use_macd_exit=use_macd_exit, macd_fast=int(macd_fast),
                    macd_slow=int(macd_slow), macd_sig=int(macd_sig),
                )

            if tdf.empty:
                st.error("No trades generated. Try adjusting thresholds, exit rules, "
                         "or the date range.")
            else:
                equity  = build_equity_curve(tdf, total_cap)
                metrics = compute_metrics(tdf, equity, total_cap)
                st.session_state["screener_results"] = dict(
                    tdf=tdf, equity=equity, metrics=metrics, failed=failed,
                    total_cap=total_cap, sel_stocks=sel_stocks,
                    s_start=pd.Timestamp(s_start), s_end=pd.Timestamp(s_end),
                )

    if "screener_results" in st.session_state:
        r          = st.session_state["screener_results"]
        tdf        = r["tdf"]
        equity     = r["equity"]
        metrics    = r["metrics"]
        failed     = r["failed"]
        total_cap  = r["total_cap"]
        sel_stocks = r["sel_stocks"]
        s_start_r  = r["s_start"]
        s_end_r    = r["s_end"]

        n50 = fetch_nifty50()
        bnh = buy_and_hold_series(sel_stocks, "1d", start_date=equity.index[0])

        if failed:
            st.warning(f"⚠️ No data for: {', '.join(failed)}")

        first_trade  = tdf["entry_date"].min().date()
        last_trade   = tdf["exit_date"].max().date()
        years_tested = (tdf["exit_date"].max() - tdf["entry_date"].min()).days / 365.25
        st.success(
            f"📅 **Configured:** {s_start_r.date()} → {s_end_r.date()}  |  "
            f"**First actual trade:** {first_trade}  |  "
            f"**Last actual trade:** {last_trade}  ({years_tested:.1f} years)"
        )

        with st.expander("📊 Per-symbol data range"):
            sym_summary = (
                tdf.groupby("symbol")
                .agg(first_trade=("entry_date", "min"),
                     last_trade=("exit_date", "max"),
                     num_trades=("net_pnl", "count"),
                     net_pnl=("net_pnl", "sum"))
                .reset_index()
                .sort_values("first_trade")
            )
            sym_summary["first_trade"] = sym_summary["first_trade"].dt.date
            sym_summary["last_trade"]  = sym_summary["last_trade"].dt.date
            sym_summary["net_pnl"]     = sym_summary["net_pnl"].map("₹{:,.0f}".format)
            st.dataframe(sym_summary, use_container_width=True)

        show_metrics(metrics, "Nifty 500 Momentum Screener")
        st.plotly_chart(
            equity_chart(equity, n50, bnh,
                         "Nifty 500 Momentum Screener — Equity Curve vs Benchmarks"),
            use_container_width=True,
        )
        st.plotly_chart(drawdown_chart(equity), use_container_width=True)

        st.plotly_chart(
            market_exposure_chart(tdf, equity),
            use_container_width=True,
        )

        with st.expander("📅 Strategy Deployment Timeline (per stock)"):
            st.caption(
                "Green = profitable trade in progress | "
                "Red = losing trade in progress | "
                "Gap = idle (no position)"
            )
            st.plotly_chart(
                deployment_timeline_chart(
                    tdf, "Nifty 500 Screener — Deployed vs Idle Periods per Symbol"
                ),
                use_container_width=True,
            )

        ca, cb = st.columns(2)
        with ca:
            st.plotly_chart(pnl_dist_chart(tdf), use_container_width=True)
        with cb:
            st.plotly_chart(per_symbol_chart(tdf), use_container_width=True)

        exit_reason_breakdown(tdf)
        show_trade_log(tdf, "nifty500_screener_backtest_trades.csv")

# ════════════════════════════════════════════════════════════
# TAB 4 — N200 HEIKIN-ASHI MACD STRATEGY
# ════════════════════════════════════════════════════════════

with tab4:
    st.subheader("N200 Heikin-Ashi MACD — Monthly Filter + Weekly Trigger")
    st.caption(
        "Replicates n200_MACD.py's screener as a backtest. Entry requires "
        "**Stage 1 (Consider)** — % from ATH below threshold, Monthly HA-MACD(12,24,3) "
        "> Signal, Monthly HA-ROC(6) > 0, Weekly HA-MACD(12,24,3) > Signal — "
        "**AND Stage 2 (Ready for Ranking)** — this week's weekly MACD-Signal gap "
        "> 85% of last week's gap, with last week's gap already positive — "
        "**both together, always**, matching the real trading process  →  enter "
        "next week's open  |  "
        "Exit: Weekly HA-MACD(12,24,3) reverse crossover (configurable)  →  "
        "exit next week's open. Signals are computed on Heikin-Ashi candles; "
        "actual entry/exit fills always use raw (non-HA) prices."
    )

    with st.expander("⚙️ Configure & Run", expanded=True):
        n2c1, n2c2, n2c3 = st.columns([2, 1, 1])

        with n2c1:
            n2_syms = st.multiselect(
                "Select symbols  (universe: Nifty 500 list)",
                options=list(NIFTY500_STOCKS.keys()),
                default=list(NIFTY500_STOCKS.keys()), key="n2_symbols",
            )
            n2dcol1, n2dcol2 = st.columns(2)
            with n2dcol1:
                from datetime import date as date_type
                n2_start = st.date_input(
                    "Backtest from", value=date_type(2015, 1, 1),
                    min_value=date_type(2000, 1, 1), max_value=date_type.today(),
                    key="n2_start",
                )
            with n2dcol2:
                n2_end = st.date_input(
                    "Backtest to", value=date_type.today(),
                    min_value=date_type(2000, 1, 1), max_value=date_type.today(),
                    key="n2_end",
                )

        with n2c2:
            n2_pct_ath = st.number_input(
                "Max % from ATH  (entry gate)", value=25.0,
                min_value=1.0, max_value=100.0, step=1.0, key="n2_pct_ath",
            )
            st.caption(
                "Entry always requires Stage 1 **and** Stage 2 together "
                "(not configurable — this matches how you actually trade "
                "it, so it can't be misconfigured into a dead combination)."
            )
            n2_log_signals = st.checkbox(
                "Log every Ready-for-Ranking signal to Google Sheets",
                value=False, key="n2_log_signals",
                help="Writes every historical week Stage 1 + Stage 2 both "
                     "confirmed (whether or not a trade was taken that "
                     "week) to the 'N200 Backtest Signals' tab in the "
                     "'Momentum Watch list - Harish' spreadsheet — an "
                     "audit trail independent of the trade log below.",
            )

        with n2c3:
            n2_cash = st.number_input("Cash per symbol (₹)", value=10000, step=1000,
                                      key="n2_cash")
            n2_lev = st.selectbox(
                "Leverage", [1, 2, 3, 4, 5], index=0,
                format_func=lambda x: f"{x}x  ({'CNC' if x == 1 else 'MTF'})",
                key="n2_lev",
            )
            n2_rate = st.number_input("MTF rate (% p.a.)", value=14.0,
                                      min_value=0.0, max_value=30.0, step=0.5,
                                      key="n2_rate") / 100

        n2_run = st.button("🚀 Run Backtest", type="primary",
                           use_container_width=True, key="n2_run")

    with st.expander("🎯 Exit Rules", expanded=False):
        st.caption(
            "Weekly MACD reverse crossover is the primary exit (as requested). "
            "The extras below are optional — combine as many as you like."
        )
        n2xc1, n2xc2 = st.columns(2)
        with n2xc1:
            n2_exit_trig = st.selectbox(
                "Weekly MACD exit trigger", key="n2_exit_trig",
                options=["crossover", "below_signal", "below_zero"],
                format_func=lambda x: {
                    "crossover":    "MACD crosses below Signal ↓  (default)",
                    "below_signal": "MACD already < Signal  (no crossover needed)",
                    "below_zero":   "MACD crosses below Zero line  (stay longer)",
                }[x],
            )
            n2_target = st.number_input(
                "Target % from entry  (0 = off)", value=0.0,
                min_value=0.0, max_value=100.0, step=0.5, key="n2_target",
            ) / 100
        with n2xc2:
            n2_stop = st.number_input(
                "Stop Loss % from entry  (0 = off)", value=0.0,
                min_value=0.0, max_value=50.0, step=0.5, key="n2_stop",
            ) / 100
            n2_trail = st.number_input(
                "Trailing Stop % from peak  (0 = off)", value=0.0,
                min_value=0.0, max_value=30.0, step=0.5, key="n2_trail",
            ) / 100
            n2_maxhold = st.number_input(
                "Max Holding Days  (0 = off)", value=0,
                min_value=0, max_value=730, step=1, key="n2_maxhold",
            )

    if n2_run:
        if not n2_syms:
            st.error("Select at least one stock.")
        else:
            sel_stocks = {k: NIFTY500_STOCKS[k] for k in n2_syms}
            total_cap  = n2_cash * len(sel_stocks)

            st.info(
                f"Running on **{len(sel_stocks)} stocks** | "
                f"₹{n2_cash:,} × {n2_lev}x = ₹{n2_cash * n2_lev:,} per stock | "
                f"Total capital: ₹{total_cap:,} | "
                f"Period: **{n2_start} → {n2_end}**"
            )
            if len(sel_stocks) > 50:
                st.warning(
                    f"Fetching {len(sel_stocks)} stocks can take several minutes on "
                    "the first run. Data is cached — subsequent runs with different "
                    "parameters are instant."
                )

            with st.spinner("Fetching data & running backtest..."):
                tdf, failed, signals = run_n200_backtest(
                    sel_stocks, n2_cash, int(n2_lev), n2_rate,
                    start_date=pd.Timestamp(n2_start), end_date=pd.Timestamp(n2_end),
                    pct_ath_max=n2_pct_ath,
                    exit_trigger=n2_exit_trig,
                    target_pct=n2_target, stop_loss_pct=n2_stop,
                    trailing_stop_pct=n2_trail, max_hold_days=int(n2_maxhold),
                    collect_signals=n2_log_signals,
                )

            if n2_log_signals:
                with st.spinner(f"Writing {len(signals)} signal(s) to Google Sheets..."):
                    n_written, sheet_err = log_signals_to_sheet(signals)
                if sheet_err:
                    st.warning(f"⚠️ Could not write signal log to Google Sheets: {sheet_err}")
                elif n_written:
                    st.success(
                        f"📤 Logged {n_written} historical signal(s) to "
                        f"'{N200_SIGNAL_TAB}' in '{N200_SHEET_NAME}'."
                    )
                else:
                    st.info("No Stage 1 + Stage 2 signals found to log for this run.")

            if tdf.empty:
                st.error("No trades generated. Try adjusting thresholds, exit rules, "
                         "or the date range.")
            else:
                equity  = build_equity_curve(tdf, total_cap)
                metrics = compute_metrics(tdf, equity, total_cap)
                st.session_state["n200_results"] = dict(
                    tdf=tdf, equity=equity, metrics=metrics, failed=failed,
                    total_cap=total_cap, sel_stocks=sel_stocks,
                    n2_start=pd.Timestamp(n2_start), n2_end=pd.Timestamp(n2_end),
                )

    if "n200_results" in st.session_state:
        r          = st.session_state["n200_results"]
        tdf        = r["tdf"]
        equity     = r["equity"]
        metrics    = r["metrics"]
        failed     = r["failed"]
        total_cap  = r["total_cap"]
        sel_stocks = r["sel_stocks"]
        n2_start_r = r["n2_start"]
        n2_end_r   = r["n2_end"]

        n50 = fetch_nifty50()
        bnh = buy_and_hold_series(sel_stocks, "1d", start_date=equity.index[0])

        if failed:
            st.warning(f"⚠️ No data for: {', '.join(failed)}")

        first_trade  = tdf["entry_date"].min().date()
        last_trade   = tdf["exit_date"].max().date()
        years_tested = (tdf["exit_date"].max() - tdf["entry_date"].min()).days / 365.25
        st.success(
            f"📅 **Configured:** {n2_start_r.date()} → {n2_end_r.date()}  |  "
            f"**First actual trade:** {first_trade}  |  "
            f"**Last actual trade:** {last_trade}  ({years_tested:.1f} years)"
        )

        with st.expander("📊 Per-symbol data range"):
            sym_summary = (
                tdf.groupby("symbol")
                .agg(first_trade=("entry_date", "min"),
                     last_trade=("exit_date", "max"),
                     num_trades=("net_pnl", "count"),
                     net_pnl=("net_pnl", "sum"))
                .reset_index()
                .sort_values("first_trade")
            )
            sym_summary["first_trade"] = sym_summary["first_trade"].dt.date
            sym_summary["last_trade"]  = sym_summary["last_trade"].dt.date
            sym_summary["net_pnl"]     = sym_summary["net_pnl"].map("₹{:,.0f}".format)
            st.dataframe(sym_summary, use_container_width=True)

        show_metrics(metrics, "N200 Heikin-Ashi MACD Strategy")
        st.plotly_chart(
            equity_chart(equity, n50, bnh,
                         "N200 Heikin-Ashi MACD — Equity Curve vs Benchmarks"),
            use_container_width=True,
        )
        st.plotly_chart(drawdown_chart(equity), use_container_width=True)

        st.plotly_chart(
            market_exposure_chart(tdf, equity),
            use_container_width=True,
        )

        with st.expander("📅 Strategy Deployment Timeline (per stock)"):
            st.caption(
                "Green = profitable trade in progress | "
                "Red = losing trade in progress | "
                "Gap = idle (no position)"
            )
            st.plotly_chart(
                deployment_timeline_chart(
                    tdf, "N200 Heikin-Ashi MACD — Deployed vs Idle Periods per Symbol"
                ),
                use_container_width=True,
            )

        ca2, cb2 = st.columns(2)
        with ca2:
            st.plotly_chart(pnl_dist_chart(tdf), use_container_width=True)
        with cb2:
            st.plotly_chart(per_symbol_chart(tdf), use_container_width=True)

        exit_reason_breakdown(tdf)
        show_trade_log(tdf, "n200_ha_macd_backtest_trades.csv")
