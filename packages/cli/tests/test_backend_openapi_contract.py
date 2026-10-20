"""文件功能：使用相邻 Backend 实时生成的 OpenAPI 验证全部 CLI 映射，避免模拟契约掩盖漂移。"""

import json
from pathlib import Path
import subprocess

import pytest

from wp.cli import main
from wp.openapi_contracts import validate_registered_contracts
from wp.output_fields import FONT_FACE_FIELDS


def test_current_backend_contract():
    """不启动服务或读取数据库，直接生成 Backend 当前契约并校验。"""
    root = Path(__file__).resolve().parents[3]
    backend = root.parent / 'web-presentation/backend'
    if not backend.is_dir():
        pytest.skip('需要相邻 web-presentation 仓库执行跨仓契约验证')
    result = subprocess.run(['uv', 'run', '--project', str(backend), 'python', '-c',
                             'import json; from app.main import app; print(json.dumps(app.openapi()))'],
                            cwd=backend, capture_output=True, text=True, encoding='utf-8', check=True, timeout=60)
    document = json.loads(result.stdout)
    validate_registered_contracts(main, document)
    # 响应字段也必须来自真实契约，避免 Mock 与投影同时使用错误字段而假绿。
    response_fields = document['components']['schemas']['WorkspaceFontConfigResponse']['properties']
    assert set(FONT_FACE_FIELDS) <= response_fields.keys()
