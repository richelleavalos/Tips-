"""Copia solamente los archivos asignados a este paquete, sin crear commits."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repositorio', help='Ruta al clon Git del integrante')
    parser.add_argument('--aplicar', action='store_true', help='Copiar los archivos; sin esta opción solo se comprueba')
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    manifest = json.loads((package / 'MANIFIESTO.json').read_text(encoding='utf-8'))
    repo = Path(args.repositorio).expanduser().resolve()
    def git(*values):
        return subprocess.check_output(['git', '-C', str(repo), *values], text=True).strip()
    if Path(git('rev-parse', '--show-toplevel')).resolve() != repo:
        raise SystemExit('Indica la raíz del repositorio, no una subcarpeta.')
    branch = git('branch', '--show-current')
    if branch != manifest['rama']:
        raise SystemExit(f'No se copió nada. Rama esperada: {manifest["rama"]}; actual: {branch or "HEAD separado"}.')
    if git('diff', '--name-only') or git('diff', '--cached', '--name-only'):
        raise SystemExit('Hay cambios versionados pendientes. Guárdalos antes de aplicar el paquete.')
    changed = []
    tracked = set(subprocess.check_output(['git', '-C', str(repo), 'ls-files', '-z']).decode().split('\0'))
    for name, digest in manifest['archivos_sha256'].items():
        source, destination = package / 'codigo' / name, repo / name
        if not destination.resolve().is_relative_to(repo):
            raise SystemExit(f'Destino fuera del repositorio: {name}')
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise SystemExit(f'El archivo del paquete cambió: {name}')
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            raise SystemExit(f'El destino no es un archivo normal: {name}')
        if destination.exists() and destination.read_bytes() == source.read_bytes():
            continue
        if destination.exists() and name not in tracked:
            raise SystemExit(f'No se sobrescribirá un archivo local sin seguimiento: {name}')
        changed.append(name)
    print(f'Rama: {branch}. Archivos del paquete: {len(manifest["archivos_sha256"])}. Cambios: {len(changed)}.')
    if not args.aplicar:
        print('Revisión terminada sin copiar archivos. Añade --aplicar para copiarlos.')
        return
    if git('branch', '--show-current') != manifest['rama']:
        raise SystemExit('La rama cambió; no se copió nada.')
    backup = Path(tempfile.mkdtemp(prefix='tips-respaldo-paquete-')) if changed else None
    for name in changed:
        target = repo / name
        if target.exists():
            saved = backup / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(package / 'codigo' / name, target)
    print('Archivos copiados. No se ejecutaron git add, commit, push ni merge.')
    if backup:
        print(f'Respaldo de los archivos reemplazados: {backup}')
    print('Revisa git diff y git status antes de preparar tu commit.')


if __name__ == '__main__':
    main()
