"""레거시 포맷(.hwp/.doc) → 새 포맷(.hwpx/.docx) 자동 변환.

Windows + 한컴오피스 + MS Word 설치 환경에서 COM 자동화로 일괄 변환.

사용법:
    python scripts/convert_legacy.py [src_dir] [dst_dir]
    기본: src=sample/, dst=sample/ (원본 옆에 변환본 저장)
"""

from __future__ import annotations

import sys
from pathlib import Path

import win32com.client


def convert_hwp_to_hwpx(src: Path, dst: Path) -> None:
    """한컴오피스 COM으로 .hwp → .hwpx 변환."""
    hwp = win32com.client.gencache.EnsureDispatch('HWPFrame.HwpObject')
    try:
        # 보안 경고/매크로 다이얼로그 우회
        hwp.RegisterModule('FilePathCheckDLL', 'AutomationModule')
        opened = hwp.Open(str(src.resolve()), 'HWP', 'forceopen:true;suspendpassword:true')
        if not opened:
            raise RuntimeError(f'한컴 Open 실패: {src}')
        # HWPX 포맷으로 저장 — 한컴 SaveAs는 Format='HWPX' (대문자)
        saved = hwp.SaveAs(str(dst.resolve()), 'HWPX')
        if not saved:
            raise RuntimeError(f'한컴 SaveAs 실패: {dst}')
    finally:
        try:
            hwp.Clear(option=1)  # 변경사항 버림
        except Exception:
            pass
        try:
            hwp.Quit()
        except Exception:
            pass


# MS Word SaveAs 포맷 상수
WD_FORMAT_XML_DOCUMENT = 12  # .docx (Office Open XML)


def convert_doc_to_docx(src: Path, dst: Path) -> None:
    """MS Word COM으로 .doc → .docx 변환."""
    word = win32com.client.gencache.EnsureDispatch('Word.Application')
    word.Visible = False
    word.DisplayAlerts = False
    try:
        doc = word.Documents.Open(
            str(src.resolve()),
            ConfirmConversions=False,
            ReadOnly=True,
        )
        doc.SaveAs2(str(dst.resolve()), FileFormat=WD_FORMAT_XML_DOCUMENT)
        doc.Close(SaveChanges=False)
    finally:
        try:
            word.Quit()
        except Exception:
            pass


def convert_directory(src_dir: Path, dst_dir: Path) -> dict:
    """디렉토리의 모든 .hwp/.doc 파일을 변환. 결과 요약 반환."""
    if not src_dir.exists():
        raise FileNotFoundError(f'디렉토리 없음: {src_dir}')
    dst_dir.mkdir(parents=True, exist_ok=True)

    summary = {'converted': [], 'skipped': [], 'failed': []}

    for src in sorted(src_dir.iterdir()):
        suffix = src.suffix.lower()
        if suffix == '.hwp':
            dst = dst_dir / (src.stem + '.hwpx')
            if dst.exists():
                summary['skipped'].append(str(dst.name))
                continue
            try:
                print(f'변환 중: {src.name} → {dst.name}')
                convert_hwp_to_hwpx(src, dst)
                summary['converted'].append(str(dst.name))
            except Exception as exc:
                summary['failed'].append(f'{src.name}: {exc}')
                print(f'  실패: {exc}')
        elif suffix == '.doc':
            dst = dst_dir / (src.stem + '.docx')
            if dst.exists():
                summary['skipped'].append(str(dst.name))
                continue
            try:
                print(f'변환 중: {src.name} → {dst.name}')
                convert_doc_to_docx(src, dst)
                summary['converted'].append(str(dst.name))
            except Exception as exc:
                summary['failed'].append(f'{src.name}: {exc}')
                print(f'  실패: {exc}')

    return summary


def main(argv: list[str]) -> int:
    src_dir = Path(argv[0]) if len(argv) > 0 else Path('sample')
    dst_dir = Path(argv[1]) if len(argv) > 1 else src_dir

    summary = convert_directory(src_dir, dst_dir)

    print()
    print('=== 변환 결과 ===')
    print(f'  성공: {len(summary["converted"])}건')
    for name in summary['converted']:
        print(f'    + {name}')
    if summary['skipped']:
        print(f'  건너뜀(이미 있음): {len(summary["skipped"])}건')
        for name in summary['skipped']:
            print(f'    - {name}')
    if summary['failed']:
        print(f'  ❌ 실패: {len(summary["failed"])}건')
        for line in summary['failed']:
            print(f'    {line}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
