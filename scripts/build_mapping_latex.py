"""Convert the project's mapping note into a self-contained LaTeX source."""
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/simulation/image-to-birdseye-pixel-mapping.md"
OUTPUT = ROOT / "output/pdf"


def escape(text):
    mapping = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%",
               "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{",
               "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(mapping.get(c, c) for c in text)


def inline(text):
    parts = re.split(r"(\\\(.*?\\\))", text)
    rendered = []
    for part in parts:
        if part.startswith(r"\("):
            rendered.append(part)
            continue
        # Keep descriptive labels; code paths are listed in the source document.
        part = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", part)
        chunks = re.split(r"(\*\*.*?\*\*)", part)
        rendered.append("".join(
            r"\textbf{" + escape(c[2:-2]) + "}" if c.startswith("**") else escape(c)
            for c in chunks))
    return "".join(rendered)


def build():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "captures/metric_rail/20260913_221200/00_panel.png",
                 OUTPUT / "mapping-comparison.png")
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    body = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("# "):
            i += 1
            continue
        if line.startswith("## "):
            title = re.sub(r"^\d+\.\s*", "", line[3:])
            body.append(r"\Needspace{12\baselineskip}\section{" + inline(title) + "}")
        elif line == r"\[":
            equation = []
            i += 1
            while lines[i].strip() != r"\]":
                equation.append(lines[i])
                i += 1
            body.append("\\[\n" + "\n".join(equation) + "\n\\]")
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [x.strip() for x in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r"[-: ]+", x) for x in cells):
                    rows.append(cells)
                i += 1
            count = len(rows[0])
            fractions = {2: [.47, .47], 3: [.27, .43, .24], 4: [.27, .22, .12, .31]}[count]
            spec = "".join(r">{\raggedright\arraybackslash}p{" + str(f) + r"\linewidth}" for f in fractions)
            body.append(r"{\small\setlength{\tabcolsep}{3pt}\begin{longtable}{" + spec + r"}\toprule")
            body.append(" & ".join(r"\textbf{" + inline(c) + "}" for c in rows[0]) + r"\\\midrule\endhead")
            for row in rows[1:]:
                body.append(" & ".join(inline(c) for c in row) + r"\\")
            body.append(r"\bottomrule\end{longtable}}")
            continue
        elif re.match(r"^(- |\d+\. )", line):
            numbered = bool(re.match(r"^\d+\. ", line))
            env = "enumerate" if numbered else "itemize"
            pattern = r"^\d+\. " if numbered else r"^- "
            body.append(r"\begin{" + env + "}")
            while i < len(lines) and re.match(pattern, lines[i].strip()):
                body.append(r"\item " + inline(re.sub(pattern, "", lines[i].strip())))
                i += 1
            body.append(r"\end{" + env + "}")
            continue
        elif line.startswith("!["):
            body.append(r"\begin{figure}[htbp]\centering"
                        r"\includegraphics[width=\linewidth]{mapping-comparison.png}"
                        r"\caption{左：原始相机图像；中：按地面 $Z=0$ 投影；右：按轨面高度校正并叠加YOLO结果。}"
                        r"\end{figure}")
        elif lines[i].startswith("    "):
            flow = []
            while i < len(lines) and lines[i].startswith("    "):
                flow.append(lines[i].strip())
                i += 1
            body.append(r"\begin{quote}\small " + r"\\ ".join(inline(x) for x in flow) + r"\end{quote}")
            continue
        elif line:
            body.append(inline(line) + "\n")
        else:
            body.append("")
        i += 1
    preamble = r"""\documentclass[UTF8,a4paper,11pt,fontset=windows]{ctexart}
\usepackage[margin=23mm,headheight=16pt]{geometry}
\usepackage{amsmath,amssymb,graphicx,array,longtable,booktabs}
\usepackage{xcolor,fancyhdr,needspace}
\usepackage[hidelinks,unicode]{hyperref}
\definecolor{ink}{HTML}{19384A}
\ctexset{section={format=\Large\bfseries\color{ink}}}
\setlength{\parskip}{4pt}
\raggedbottom
\setlength{\emergencystretch}{3em}
\renewcommand{\arraystretch}{1.25}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\small 无人机轨道视觉 / 像素映射}
\fancyhead[R]{\small 技术说明}
\fancyfoot[C]{\thepage}
\title{\bfseries 原始俯视图与鸟瞰图\\的像素映射关系}
\author{UAV Control Demo}
\date{2026年9月13日}
\begin{document}
\maketitle
\thispagestyle{fancy}
\noindent\textbf{核心关系：}
原始图像经过去畸变后，先映射到轨道平面的米制坐标，再映射到鸟瞰像素网格：
\[
\boxed{H_{\mathrm{bev}}(t)=S\,H_g^{-1}(t)}
\]
"""
    tex = preamble + "\n".join(body) + "\n\\end{document}\n"
    path = OUTPUT / "image-to-birdseye-pixel-mapping.tex"
    path.write_text(tex, encoding="utf-8")
    print(path)


if __name__ == "__main__":
    build()
