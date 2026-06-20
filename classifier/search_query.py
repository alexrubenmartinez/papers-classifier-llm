"""Cadena de búsqueda Grupo 3 — Ciberseguridad / Zero Trust + IA + Cloud Híbrido.

Refina la del enunciado agregando sinónimos técnicos (NIST 800-207, BeyondCorp,
microsegmentation, SDP, SASE) que mejoran el recall semántico contra el corpus.
"""

SEARCH_QUERY = (
    '("zero trust" OR "zero-trust architecture" OR "zero trust security" OR '
    '"zero trust model" OR "zero trust network access" OR "ZTNA" OR '
    '"BeyondCorp" OR "NIST 800-207" OR "software defined perimeter" OR "SDP" OR '
    '"SASE" OR "microsegmentation" OR "micro-segmentation" OR '
    '"arquitectura zero trust" OR "seguridad zero trust") AND '
    '("cybersecurity" OR "cyber security" OR "information security" OR '
    '"computer security" OR "network security" OR '
    '"cloud security" OR "hybrid cloud security" OR "cloud-native security" OR '
    '"seguridad informatica" OR "seguridad en la nube" OR '
    '"seguridad en nube hibrida" OR "ciberseguridad") AND '
    '("threat detection" OR "intrusion detection" OR "anomaly detection" OR '
    '"attack detection" OR "early threat detection" OR "malware detection" OR '
    '"intrusion prevention" OR "deteccion de amenazas" OR "deteccion de intrusos" OR '
    '"deteccion de anomalias" OR "deteccion temprana de ataques") AND '
    '("artificial intelligence" OR "machine learning" OR "deep learning" OR '
    '"neural network" OR "large language model" OR "transformer" OR '
    '"reinforcement learning" OR "graph neural network" OR '
    '"IA" OR "inteligencia artificial" OR "aprendizaje automatico")'
)


KEYWORDS_BY_AXIS = {
    "zero_trust": [
        "zero trust", "zero-trust", "zero trust architecture", "ztna",
        "beyondcorp", "nist 800-207", "software defined perimeter", "sdp",
        "sase", "microsegmentation", "micro-segmentation",
        "perímetro definido por software", "arquitectura zero trust",
    ],
    "cybersecurity": [
        "cybersecurity", "cyber security", "information security",
        "computer security", "network security", "cloud security",
        "hybrid cloud security", "cloud-native security",
        "ciberseguridad", "seguridad informática", "seguridad en la nube",
        "seguridad en nube híbrida",
    ],
    "detection": [
        "threat detection", "intrusion detection", "anomaly detection",
        "attack detection", "early threat detection", "malware detection",
        "intrusion prevention", "ids", "ips",
        "detección de amenazas", "detección de intrusos",
        "detección de anomalías", "detección temprana de ataques",
    ],
    "ai": [
        "artificial intelligence", "machine learning", "deep learning",
        "neural network", "large language model", "llm", "transformer",
        "reinforcement learning", "graph neural network", "gnn",
        "inteligencia artificial", "aprendizaje automático",
    ],
}


# Lista plana para iterar
ALL_KEYWORDS: list[str] = sorted({kw.lower() for axis in KEYWORDS_BY_AXIS.values() for kw in axis})


def query_as_natural_text() -> str:
    """Versión en texto natural para alimentar TF-IDF / Sentence-BERT.

    Las búsquedas booleanas confunden a los embeddings; mejor pasar la
    intención como un párrafo descriptivo.
    """
    return (
        "Zero trust architecture and zero trust network access for cybersecurity "
        "in hybrid and multi cloud environments. Early threat detection, "
        "intrusion detection, anomaly detection and malware detection using "
        "artificial intelligence, machine learning and deep learning. "
        "Microsegmentation, NIST 800-207, BeyondCorp, software defined perimeter "
        "and SASE for cloud security and information security."
    )
