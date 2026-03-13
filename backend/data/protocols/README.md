# PDF knowledge base — place offline protocol PDFs here before first run.
# Required files (recommended):
#   first_aid_manual.pdf    — Primary reference (St. John / WHO)
#   trauma_guide.pdf        — Trauma and injury protocols
#   disaster_response.pdf   — Disaster shelter management

# LlamaIndex will scan all .pdf files in this directory on startup
# and build the vector index in backend/vector_store/.
# If new PDFs are added, delete backend/vector_store/ to force a rebuild.
