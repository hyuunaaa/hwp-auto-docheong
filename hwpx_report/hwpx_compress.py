import zipfile
from pathlib import Path
from datetime import datetime


def create_hwpx_from_folder(folder_path: str, output_path: str):
    """
    폴더를 HWPX 파일로 압축
    
    Args:
        folder_path: 압축할 폴더 경로
        output_path: 출력 .hwpx 파일 경로
    
    Note:
        - mimetype은 압축하지 않고 STORED 방식으로 저장
        - 1980년 이전 타임스탬프 문제 해결을 위해 명시적으로 현재 시간 사용
    """
    
    folder = Path(folder_path)
    output = Path(output_path)
    
    print(f"\n  ZIP 생성 중: {output}")
    
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # mimetype은 STORED로 (압축 안함)
        mimetype_file = folder / 'mimetype'
        if mimetype_file.exists():
            # ✅ mimetype은 기존 방식 유지 (문제 없음)
            zipf.write(mimetype_file, 'mimetype', compress_type=zipfile.ZIP_STORED)
            print(f"    ✓ mimetype (STORED)")
        
        # 모든 파일 추가 (타임스탬프 문제 해결)
        for file_path in sorted(folder.rglob('*')):
            if file_path.is_file() and file_path.name != 'mimetype':
                arcname = file_path.relative_to(folder)
                
                # ✅ 파일 데이터 읽기
                with open(file_path, 'rb') as f:
                    file_data = f.read()
                
                # ✅ ZipInfo 객체 생성 (타임스탬프 명시적 설정)
                zip_info = zipfile.ZipInfo(
                    filename=str(arcname),
                    date_time=datetime.now().timetuple()[:6]  # 현재 시간 사용 (1980년 이전 문제 해결)
                )
                zip_info.compress_type = zipfile.ZIP_DEFLATED
                
                # ✅ 원본 파일 권한 유지 (선택사항)
                try:
                    zip_info.external_attr = file_path.stat().st_mode << 16
                except:
                    pass
                
                # ✅ 파일 쓰기
                zipf.writestr(zip_info, file_data)
                
                if file_path.suffix == '.xml':
                    print(f"    ✓ {arcname} (DEFLATED)")
    
    print(f"✅ 압축 완료: {output}\n")