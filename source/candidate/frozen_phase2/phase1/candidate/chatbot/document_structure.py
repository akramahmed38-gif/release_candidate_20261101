"""Preserve paragraphs, table rows and nearby qualifications without inventing cells."""
import re


def structured_chunks(text,size=900,overlap=150):
    lines=[line.strip() for line in str(text or '').replace('\r\n','\n').replace('\r','\n').split('\n')]
    units=[];paragraph=[]
    def flush():
        if paragraph:units.append('\n'.join(paragraph));paragraph.clear()
    for line in lines:
        if not line:flush();continue
        if '|' in line or '\t' in line:
            flush();units.append(line.replace('\t',' | '));continue
        if re.match(r'^(?:بشرط|فقط|باستثناء|يشترط|تطبق|provided|only|except|subject to)\b',line,re.I):
            flush()
            if units:units[-1]+='\n'+line
            else:units.append(line)
        elif sum(len(s) for s in paragraph)+len(line)>size and paragraph:
            flush();paragraph.append(line)
        else:paragraph.append(line)
    flush()
    chunks=[];current=[];length=0
    for unit in units:
        if current and length+len(unit)+2>size:
            chunks.append('\n\n'.join(current))
            tail=current[-1] if len(current[-1])<=overlap else None
            current=[tail] if tail else [];length=len(tail) if tail else 0
        current.append(unit);length+=len(unit)+2
    if current:chunks.append('\n\n'.join(current))
    return chunks
