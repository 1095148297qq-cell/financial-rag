"""Review aids, never a substitute for source, scope and citation review."""
from decimal import Decimal, ROUND_HALF_UP
import re


def percentage_match(expected, text, places):
    """Compare percentage tokens at a declared precision (not money tokens)."""
    quantum=Decimal(1).scaleb(-places)
    target=Decimal(str(expected)).quantize(quantum,rounding=ROUND_HALF_UP)
    normalized=text.replace('％','%').replace('−','-').replace('－','-')
    values=re.findall(r'(-?\d+(?:\.\d+)?)\s*%',normalized)
    return any(Decimal(value).quantize(quantum,rounding=ROUND_HALF_UP)==target for value in values)


def citation_coverage(record, groups):
    """Each group is a list of acceptable source pages; alternatives are OR."""
    cited=sorted({int(n) for n in re.findall(r'\[(\d+)\]',record.get('answer',''))})
    invalid=[n for n in cited if not 1<=n<=len(record['chunks'])]
    sources={(c['company'],c['year'],c['page']) for n,c in enumerate(record['chunks'],1) if n in cited}
    missing=[group for group in groups if not any((r['company'],r['year'],r['page']) in sources for r in group)]
    return {'citation_numbers':cited,'invalid_citations':invalid,'missing_source_groups':missing,
            'page_coverage_pass':bool(cited) and not invalid and not missing,
            'limitation':'Page coverage is necessary only; inspect the cited row, scope, unit and year manually.'}
