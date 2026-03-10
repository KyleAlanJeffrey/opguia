#!/usr/bin/env bash
# Release script — bump version, build, tag, and push.
# Usage: ./release.sh 1.0.1

set -euo pipefail

VERSION="${1:?Usage: ./release.sh <version>}"

echo "==> Bumping version to $VERSION"
sed -i '' "s/__version__ = \".*\"/__version__ = \"$VERSION\"/" opguia/__init__.py

echo "==> Cleaning old builds"
rm -rf dist/ build/ *.egg-info

echo "==> Building"
python -m build

echo "==> Committing"
git add opguia/__init__.py
git commit -m "v$VERSION"

echo "==> Tagging v$VERSION"
git tag "v$VERSION"

echo "==> Pushing"
git push && git push --tags

echo ""
echo "Done. GitHub Actions will publish to PyPI."
echo "Or manually: twine upload dist/*"
