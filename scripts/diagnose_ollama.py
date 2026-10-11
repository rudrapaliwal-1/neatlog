"""Local-only diagnosis on the bundled BOLA example; never executes model output."""
import json
from pathlib import Path
from time import monotonic

from agent.context import build_context
from agent.edits import GUARD_SCHEMA, build_guard_diff, parse_guard_response
from agent.prompts.guard import build_guard_prompt
from agent.providers.ollama import OllamaProvider

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = (ROOT / 'verification/lab/app/access.py').read_bytes().decode('utf-8')
    finding = {'id': 'BOLA-LOCAL-DIAGNOSTIC', 'type': 'BROKEN_OBJECT_LEVEL_AUTHORIZATION',
               'severity': 'HIGH', 'file_path': 'app/access.py',
               'description': 'The document access function returns records without checking that the requesting user owns the document.'}
    context = build_context(finding, {'app/access.py': source}, {'app/access.py'})
    provider = OllamaProvider()
    started = monotonic()
    raw = provider.generate(build_guard_prompt(context, 0, None), format_schema=GUARD_SCHEMA)
    output = ROOT / 'local-audit/ollama-diagnostic-response.txt'
    output.parent.mkdir(exist_ok=True)
    output.write_text(raw, encoding='utf-8')
    result = {'model': provider.model, 'duration_seconds': round(monotonic() - started, 2),
              'response_chars': len(raw), 'response_file': str(output)}
    try:
        _, _, code = parse_guard_response(raw)
        build_guard_diff(source, 'app/access.py', code)
        result['outcome'] = 'accepted'
    except ValueError as exc:
        result.update(outcome='rejected', reason=str(exc))
    (ROOT / 'local-audit/ollama-diagnostic.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
