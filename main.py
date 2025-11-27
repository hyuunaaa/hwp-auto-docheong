from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime
import shutil
import uuid
import json

from hwpx_report.hwp_pydantic import DocheongReport, DynamicReport, DynamicSection
from hwpx_report.docheong_report import process_docheong_report, process_dynamic_report
from hwpx_report.hwpx_compress import create_hwpx_from_folder

# 🔹 LLM 자동 분류 헬퍼
try:
    from hwpx_report.model_json import generate_docheong_json, generate_dynamic_json
except ImportError:
    generate_docheong_json = None
    generate_dynamic_json = None

app = FastAPI(title="HWPX Report API", version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = BASE_DIR / "temp_outputs"
TEMP_DIR.mkdir(exist_ok=True)


# ---------- 요청 / 응답 모델 ----------

class DocheongRequest(BaseModel):
    """섹션이 이미 나뉘어 있는 요청용 JSON"""
    title: str
    overview: list[str]
    test_status: list[str]
    key_issues: list[str]
    followup: list[str]


class DocheongAutoRequest(BaseModel):
    """줄글/STT 결과 자동 분류 요청"""
    text: str
    title: str | None = None


class DynamicSectionRequest(BaseModel):
    """동적 섹션 요청"""
    header: str
    content: list[str]


class DynamicReportRequest(BaseModel):
    """동적 섹션 보고서 요청"""
    title: str
    sections: list[DynamicSectionRequest]


class DynamicAutoRequest(BaseModel):
    """줄글/STT 결과 동적 섹션 자동 분류"""
    text: str
    title: str | None = None


class ReportResponse(BaseModel):
    success: bool
    message: str
    file_id: str
    download_url: str


# ---------- 템플릿 경로 헬퍼 ----------

def _get_template_dir(template_name: str = "default") -> Path:
    """
    템플릿 이름에 따라 적절한 템플릿 폴더를 반환
    
    Args:
        template_name: "default" (기본 템플릿) 또는 "v2" (V2 템플릿)
    
    Returns:
        템플릿 폴더 경로
    """
    base_template_dir = BASE_DIR / "hwpx_report" / "template"
    
    if template_name == "v2":
        candidates = [
            base_template_dir / "docheong_template2",
            base_template_dir / "도청동향보고서V2_템플릿",
        ]
        template_type = "V2"
    else:
        candidates = [
            base_template_dir / "docheong_template",
            base_template_dir / "도청동향보고서_템플릿",
        ]
        template_type = "기본"

    for p in candidates:
        if p.exists():
            return p

    raise FileNotFoundError(
        f"{template_type} 템플릿 폴더를 찾을 수 없습니다. 시도한 경로: "
        + ", ".join(str(p) for p in candidates)
    )


# ---------- 공통 HWPX 생성 로직 ----------

def _create_docheong_hwpx(
    report: DocheongReport, 
    template_name: str = "default"
) -> tuple[str, Path]:
    """
    도청 보고서 HWPX 생성
    
    Args:
        report: DocheongReport 객체
        template_name: 사용할 템플릿 ("default" 또는 "v2")
    
    Returns:
        (file_id, hwpx_output_path)
    """
    file_id = f"docheong_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    
    if template_name == "v2":
        file_id = f"docheong_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    # 1) JSON 저장
    json_path = TEMP_DIR / f"{file_id}.json"
    data = report.model_dump()
    json_text = json.dumps(data, ensure_ascii=False, indent=2)
    json_path.write_text(json_text, encoding="utf-8")

    # 2) 템플릿 복사 (선택된 템플릿 사용)
    template_src = _get_template_dir(template_name)
    work_dir = TEMP_DIR / file_id
    shutil.copytree(template_src, work_dir)

    # 3) XML 변환
    xml_template = work_dir / "Contents/section0.xml"
    xml_output = work_dir / "Contents/section0.xml"
    process_docheong_report(str(json_path), str(xml_template), str(xml_output))

    # 4) HWPX 압축 생성
    hwpx_output = TEMP_DIR / f"{file_id}.hwpx"
    create_hwpx_from_folder(str(work_dir), str(hwpx_output))

    return file_id, hwpx_output


def _create_dynamic_hwpx(
    report: DynamicReport,
    template_name: str = "default"
) -> tuple[str, Path]:
    """
    동적 섹션 HWPX 생성
    
    Args:
        report: DynamicReport 객체
        template_name: 사용할 템플릿 ("default" 또는 "v2")
    
    Returns:
        (file_id, hwpx_output_path)
    """
    file_id = f"dynamic_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    # 1) JSON 저장
    json_path = TEMP_DIR / f"{file_id}.json"
    data = report.model_dump()
    json_text = json.dumps(data, ensure_ascii=False, indent=2)
    json_path.write_text(json_text, encoding="utf-8")

    # 2) 템플릿 복사 (선택된 템플릿 사용)
    template_src = _get_template_dir(template_name)
    work_dir = TEMP_DIR / file_id
    shutil.copytree(template_src, work_dir)

    # 3) XML 변환
    xml_template = work_dir / "Contents/section0.xml"
    xml_output = work_dir / "Contents/section0.xml"
    process_dynamic_report(str(json_path), str(xml_template), str(xml_output))

    # 4) HWPX 압축 생성
    hwpx_output = TEMP_DIR / f"{file_id}.hwpx"
    create_hwpx_from_folder(str(work_dir), str(hwpx_output))

    return file_id, hwpx_output


# ---------- 엔드포인트 ----------

@app.get("/")
async def root():
    return {
        "service": "HWPX Report Generator",
        "status": "running",
        "port": 5001,
        "endpoints": {
            "generate": "POST /api/report/generate (원스텝: 텍스트→파일)",
            "docheong": "POST /api/report/docheong",
            "docheong_auto": "POST /api/report/docheong-auto",
            "dynamic": "POST /api/report/dynamic",
            "dynamic_auto": "POST /api/report/dynamic-auto",
            "download": "GET /api/download/{file_id}",
            "cleanup": "DELETE /api/cleanup/{file_id}",
        },
        "template_options": {
            "default": "기본 도청 템플릿",
            "v2": "V2 템플릿 (docheong_template2)"
        }
    }


@app.post("/api/report/docheong", response_model=ReportResponse)
async def create_docheong_report(
    request: DocheongRequest,
    template_name: str = Query(
        "default",
        description="사용할 템플릿 선택",
        enum=["default", "v2"]
    )
):
    """
    섹션이 이미 나뉜 JSON을 받는 엔드포인트
    
    **템플릿 선택:**
    - `default`: 기본 도청 템플릿 (docheong_template)
    - `v2`: V2 템플릿 (docheong_template2)
    """
    try:
        report = DocheongReport(**request.dict())
        file_id, _ = _create_docheong_hwpx(report, template_name)

        return ReportResponse(
            success=True,
            message=f"도청 보고서 생성 완료 (템플릿: {template_name})",
            file_id=file_id,
            download_url=f"/api/download/{file_id}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/report/docheong-auto", response_model=ReportResponse)
async def create_docheong_report_auto(
    request: DocheongAutoRequest,
    template_name: str = Query(
        "default",
        description="사용할 템플릿 선택",
        enum=["default", "v2"]
    )
):
    """
    줄글/STT 결과 자동 분류 후 보고서 생성
    
    **템플릿 선택:**
    - `default`: 기본 도청 템플릿
    - `v2`: V2 템플릿
    """
    if generate_docheong_json is None:
        raise HTTPException(
            status_code=500,
            detail="자동 분류 기능이 비활성화되어 있습니다."
        )

    try:
        report_json = generate_docheong_json(request.text)
        if request.title:
            report_json["title"] = request.title

        report = DocheongReport(**report_json)
        file_id, _ = _create_docheong_hwpx(report, template_name)

        return ReportResponse(
            success=True,
            message=f"도청 보고서(자동 분류) 생성 완료 (템플릿: {template_name})",
            file_id=file_id,
            download_url=f"/api/download/{file_id}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/report/dynamic", response_model=ReportResponse)
async def create_dynamic_report(
    request: DynamicReportRequest,
    template_name: str = Query(
        "default",
        description="사용할 템플릿 선택",
        enum=["default", "v2"]
    )
):
    """
    동적 섹션 보고서 생성
    
    **템플릿 선택:**
    - `default`: 기본 템플릿
    - `v2`: V2 템플릿
    """
    try:
        sections = [
            DynamicSection(header=s.header, content=s.content)
            for s in request.sections
        ]
        report = DynamicReport(title=request.title, sections=sections)
        file_id, _ = _create_dynamic_hwpx(report, template_name)

        return ReportResponse(
            success=True,
            message=f"동적 섹션 보고서 생성 완료 (템플릿: {template_name})",
            file_id=file_id,
            download_url=f"/api/download/{file_id}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/report/dynamic-auto", response_model=ReportResponse)
async def create_dynamic_report_auto(
    request: DynamicAutoRequest,
    template_name: str = Query(
        "default",
        description="사용할 템플릿 선택",
        enum=["default", "v2"]
    )
):
    """
    줄글/STT 결과로 동적 섹션 자동 분류 후 보고서 생성
    
    **템플릿 선택:**
    - `default`: 기본 템플릿
    - `v2`: V2 템플릿
    """
    if generate_dynamic_json is None:
        raise HTTPException(
            status_code=500,
            detail="동적 섹션 자동 분류 기능이 비활성화되어 있습니다."
        )

    try:
        report_json = generate_dynamic_json(request.text)
        if request.title:
            report_json["title"] = request.title

        report = DynamicReport(**report_json)
        file_id, _ = _create_dynamic_hwpx(report, template_name)

        return ReportResponse(
            success=True,
            message=f"동적 섹션 보고서(자동 분류) 생성 완료 (템플릿: {template_name})",
            file_id=file_id,
            download_url=f"/api/download/{file_id}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/report/generate")
async def generate_report_direct(
    request: DynamicAutoRequest,
    template_name: str = Query(
        "default",
        description="사용할 템플릿 선택",
        enum=["default", "v2"]
    )
):
    """
    원스텝 파이프라인: 텍스트 → 자동 섹션 구성 → HWPX 파일 직접 반환
    
    **템플릿 선택:**
    - `default`: 기본 템플릿
    - `v2`: V2 템플릿
    """
    if generate_dynamic_json is None:
        raise HTTPException(
            status_code=500,
            detail="동적 섹션 자동 분류 기능이 비활성화되어 있습니다."
        )

    try:
        report_json = generate_dynamic_json(request.text)
        if request.title:
            report_json["title"] = request.title

        report = DynamicReport(**report_json)
        file_id, hwpx_path = _create_dynamic_hwpx(report, template_name)

        safe_title = report.title.replace(" ", "_").replace("/", "_")[:50]
        filename = f"{safe_title}_{file_id}.hwpx"

        return FileResponse(
            path=hwpx_path,
            media_type="application/vnd.hancom.hwpx",
            filename=filename,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/download/{file_id}")
async def download_report(file_id: str):
    """생성된 보고서 다운로드"""
    hwpx_file = TEMP_DIR / f"{file_id}.hwpx"

    if not hwpx_file.exists():
        raise HTTPException(status_code=404, detail="파일 없음")

    return FileResponse(
        path=hwpx_file,
        media_type="application/vnd.hancom.hwpx",
        filename=f"{file_id}.hwpx",
    )


@app.delete("/api/cleanup/{file_id}")
async def cleanup_report(file_id: str):
    """생성된 파일 정리"""
    try:
        (TEMP_DIR / f"{file_id}.hwpx").unlink(missing_ok=True)
        (TEMP_DIR / f"{file_id}.json").unlink(missing_ok=True)
        work_dir = TEMP_DIR / file_id
        if work_dir.exists():
            shutil.rmtree(work_dir)
        return {"success": True, "message": "삭제 완료"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)