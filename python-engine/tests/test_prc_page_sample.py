"""Regression test using an Owner-supplied official PRC LEPT Elementary page sample.

The source is page 2 of the March 2026 Elementary successful examinees roll.
The image was OCR-read and visually checked; these 50 rows are a representative
sample, not the complete 369-page release. This tests explicit column mapping
and Greenlight sequence coverage, not PDF acquisition or OCR itself.
"""
from processor.normalizer import normalize_extracted_tables
from processor.greenlight import validate_records


NAMES = [
    "AALA, DESIREE JOY DE RAMOS",
    "ABA, JUNAIRA M'LA",
    "ABABA, LADY MAMAC",
    "ABABA, TRISHA TOLENTINO",
    "ABABAT, MERRIANE BAGUIO",
    "ABACAN, KATHERINE PAGARA",
    "ABAD, CRIZA MAE GARCIA",
    "ABAD, LANLIE INAHID",
    "ABAD, ROSALIE ESCOBAR",
    "ABADA, MILMOD BRAGA",
    "ABADIANO, EDWARD JOSEPH VASQUEZ",
    "ABADIES, CARMEL JESSICA",
    "ABADILLA, ANDRIAN IRADER",
    "ABADILLA, RIZZA MAE LOPEZ",
    "ABAIS, ROGIELYN LUMAYNO",
    "ABAJERO, JAMES CARL BANGCAS",
    "ABAL, ALFAYD ARANETA",
    "ABALAJEN, ABIGAIL LIPATA",
    "ABALES, DONNA KYLA DALU-AN",
    "ABALLE, LORENA OCOY",
    "ABALLE, SHEILA MAY TIROGO",
    "ABALLE, WILBERT MAQUINTO",
    "ABALOS, CRIZEL JOY URAY",
    "ABALOS, CRYSTAL KAYE AMBON",
    "ABALOS, HONEY GHEMMALYN VISCAYNO",
    "ABALOS, KHARYL JOY DADAY",
    "ABALOS, MARY ISABEL ANTONETTE BOROY",
    "ABALOS, MHYLA CUDIAMAT",
    "ABALOS, ODESSA DURIAS",
    "ABALOS, ROMEO JR MELGO",
    "ABAN, AIREN SABUYA",
    "ABAN, CYVIL ROSE JEAN ORTEGA",
    "ABAN, DAINALYN PASCUA",
    "ABANDA, JOCELYN BAAY",
    "ABANDO, ERMA LOREZO",
    "ABANDULA, CAMILLE MONTECALVO",
    "ABANEL, DIANA JUNE MARILAG",
    "ABANES, NICOLE ANGELA CABILES",
    "ABANGAN, JAMAICA MAE BALO",
    "ABANIEL, ANGIE VILLAFRANCA",
    "ABANILLA, ANGELICA CORONACION",
    "ABANIZA, DAVE MHAR POYOTA",
    "ABANTE, BERNA CASAPAO",
    "ABANTE, JANE CHRISTINE MONTELIOLA",
    "ABANTE, JOHN MICHAEL",
    "ABAO, ALF FADULLA",
    "ABAO, JESA GALENDEZ",
    "ABAPO, CHRISTY VILCHEZ",
    "ABAPO, EARL PEPITO",
    "ABAPO, JOHANA MAE CABALLES"
]

def test_prc_lept_2026_elementary_page_2_exact_name_sequence_mapping():
    extraction = {
        "pages": [{
            "page_number": 2,
            "tables": [[
                ["Seq. No.", "Name"],
                *[[str(index), name] for index, name in enumerate(NAMES, start=1)],
            ]],
        }]
    }
    mapping = {
        "table_indexes": [0],
        "header_rows": 1,
        "sequence_column": 0,
        "name_column": 1,
    }

    records = normalize_extracted_tables(extraction, mapping)

    assert records == [
        {"sequence_number": str(index), "name": name}
        for index, name in enumerate(NAMES, start=1)
    ]
    report = validate_records(records, announced_count=50, provenance="official_direct")
    assert report["status"] == "GREENLIGHT"
    assert report["greenlight_score"] == 100
    assert report["publication_allowed"] is True
    assert report["checks"]["complete_sequence_coverage"] is True
    assert report["metrics"]["missing_sequence_count"] == 0
