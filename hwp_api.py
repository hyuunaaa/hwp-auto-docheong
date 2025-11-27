from flask import Flask, request, jsonify, send_file
from pathlib import Path
import uuid
import shutil
import os

from hwpx_report.hwp_pydantic import DocheongReport
from hwpx_report.docheong_report import process_docheong_report
from hwpx_report.jbnu_report import copy_folder, zip_as_hwpx

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent

# 템플릿 경로
HWP_TEMPLATE_DEFAULT = BASE_DIR / "hwpx_report" / "template" / "docheong_template"
HWP_TEMPLATE_V2 = BASE_DIR / "hwpx_report" / "template" / "docheong_template2"

HWP_WORK_BASE = BASE_DIR / "hwpx_report" / "hwpx_file"
JSON_TMP_DIR = HWP_WORK_BASE / "json_tmp"

JSON_TMP_DIR.mkdir(parents=True, exist_ok=True)
HWP_WORK_BASE.mkdir(parents=True, exist_ok=True)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "docheong-hwp-generator"})


@app.route("/generate-docheong", methods=["POST"])
def generate_docheong():
    """
    Body(JSON)는 DocheongReport 구조.

    {
      "title": "보고서 제목",
      "overview": ["..", ".."],
      "test_status": ["..", ".."],
      "key_issues": ["..", ".."],
      "followup": ["..", ".."]
    }

    쿼리파라미터:
      - template_name=default | v2
    """

    # 1) 템플릿 선택
    template_name = request.args.get("template_name", "default")
    if template_name == "v2":
        template_root = HWP_TEMPLATE_V2
    else:
        template_root = HWP_TEMPLATE_DEFAULT

    if not template_root.exists():
        return jsonify({
            "error": "template_not_found",
            "detail": f"template folder not found: {template_root}"
        }), 500

    # 2) JSON 파싱 (silent=True 로 해서 Flask 기본 400 HTML 방지)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({
            "error": "invalid_json",
            "detail": "JSON body required and must be an object"
        }), 400

    # 3) Pydantic 검증
    try:
        report = DocheongReport(**data)
    except Exception as e:
        return jsonify({
            "error": "invalid_payload",
            "detail": str(e)
        }), 400

    # 4) 작업용 경로 세팅
    uid = uuid.uuid4().hex
    work_dir = HWP_WORK_BASE / f"도청동향보고서_복사본_{uid}"
    json_path = JSON_TMP_DIR / f"docheong_{uid}.json"
    xml_template = template_root / "Contents" / "section0.xml"
    xml_output = work_dir / "Contents" / "section0.xml"
    output_hwpx = HWP_WORK_BASE / f"docheong_{uid}.hwpx"

    try:
        # 4-1) 템플릿 폴더 복사
        copy_folder(str(template_root), str(work_dir))

        # 4-2) JSON 저장
        json_path.write_text(
            report.model_dump_json(ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        # 4-3) XML 변환
        process_docheong_report(str(json_path), str(xml_template), str(xml_output))

        # 4-4) hwpx 압축 생성
        zip_as_hwpx(str(work_dir), str(output_hwpx))

        # 4-5) 파일 응답
        return send_file(
            output_hwpx,
            as_attachment=True,
            download_name="도청동향보고서.hwpx",
            mimetype="application/octet-stream"
        )

    except Exception as e:
        return jsonify({
            "error": "generation_failed",
            "detail": str(e)
        }), 500

    finally:
        # 작업 디렉토리 정리(선택)
        try:
            if work_dir.exists():
                shutil.rmtree(work_dir)
        except Exception:
            pass


if __name__ == "__main__":
    # 디버그용 로그가 보이도록 debug=True 권장
    app.run(host="0.0.0.0", port=5010, debug=True)
