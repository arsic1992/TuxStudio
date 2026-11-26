#!/usr/bin/env python3
"""Tux Studio 0.10.2.1 — GUI prototype. Requires PySide6 >= 6.5.
Run: python TuxStudio_DEMO_0_10_0.py
Automatic saving and recovery are implemented; initial language execution is supported.
"""
import sys
import re
import math
import random
import statistics
import datetime
import os
import stat
import posixpath
import errno
import hashlib
import json
import csv
import io
import uuid
import time
import queue
import threading
import subprocess
import shutil
from pathlib import Path
from dataclasses import dataclass
import unicodedata
from bisect import bisect_right

LEXER_VERSION = '0.1.0'
class TuxLanguageRegistry:
    keywords = set('var const func type enum record class error add as if else then unless switch case default for while until repeat do forever break continue return yield guard label and or not xor in is try catch finally throw recover attempt retry assert using defer me init extends override private protected public static outer true false null program permissions limits'.split())
    contextual = set('step with index along strict where take skip completed empty check when otherwise pure cached alias ensures result readonly copy ref collect from on backoff require optional reason pattern capture use start end exactly either literal digit letter group oneOf except'.split())
    types = set('int int8 int16 int32 int64 uint8 uint16 uint32 uint64 float decimal complex bool string char byte bytes buffer list tuple dict set range array matrix stack queue deque any secret path result void'.split())
    builtins = set('display write newline displayError displayWarning displaySuccess displayInfo input inputPassword inputKey inputChar inputLines confirm choose chooseMany pause len copy deepCopy even odd prime positive negative zero nonzero whole empty nonempty uppercase lowercase alphabetic numeric alphanumeric all any none exactly atLeast atMost min max abs round pow sum type sameObject help exit style rgb B KB MB GB TB KiB MiB GiB TiB seconds milliseconds minutes hours days ok failed'.split())
    operators = sorted('@= **= //= <<= >>= ??= ... ..< ++ -- ** // ?? ?. |> => == != <= >= << >> += -= *= /= %= &= |= ^= .. + - * / % @ & | ^ ~ < > = ! ? . :'.split(), key=len, reverse=True)

@dataclass(frozen=True)
class TuxToken:
    kind: str
    text: str
    start: int
    end: int
    line: int
    column: int

@dataclass(frozen=True)
class TuxDiagnostic:
    code: str
    message: str
    start: int
    end: int
    suggestion: str = ''

@dataclass
class TuxLexResult:
    tokens: list
    diagnostics: list

class TuxLexer:
    operator_groups = {c: tuple(op for op in TuxLanguageRegistry.operators if op[0] == c) for c in {op[0] for op in TuxLanguageRegistry.operators}}
    number = re.compile(r'(?:0[xX][0-9a-fA-F]+(?:_[0-9a-fA-F]+)*|0[bB][01]+(?:_[01]+)*|0[oO][0-7]+(?:_[0-7]+)*|[0-9]+(?:_[0-9]+)*(?:\.[0-9]+(?:_[0-9]+)*)?(?:[eE][+-]?[0-9]+(?:_[0-9]+)*)?i?)\Z')
    def lex(self, source):
        self.s=source; self.i=0; self.tokens=[]; self.diagnostics=[]; self.depth=0
        self.lines=[0]+[m.end() for m in re.finditer('\n',source)]
        while self.i<len(source): self.scan()
        self.emit('EOF',self.i,self.i)
        return TuxLexResult(self.tokens,self.diagnostics)
    def emit(self,k,a,b):
        line=bisect_right(self.lines,a); self.tokens.append(TuxToken(k,self.s[a:b],a,b,line,a-self.lines[line-1]+1))
    def error(self,n,msg,a,b,suggestion='',warning=False):
        self.diagnostics.append(TuxDiagnostic(f'TUX-{ "W" if warning else "E"}-LEX-{n:03}',msg,a,b,suggestion))
    def scan(self):
        s=self.s; a=self.i; c=s[a]; n=len(s)
        if c=='\n': self.i+=1; self.emit('NEWLINE',a,self.i); return
        if c in ' \t\r':
            while self.i<n and s[self.i] in ' \t\r': self.i+=1
            self.emit('WHITESPACE',a,self.i); return
        if c=='#':
            end=s.find('\n',a); self.i=n if end<0 else end; self.emit('DOCUMENTATION' if s.startswith('##',a) else 'COMMENT',a,self.i); return
        if s.startswith('/*',a):
            self.i+=2; depth=1
            while self.i<n and depth:
                if s.startswith('/*',self.i): depth+=1; self.i+=2
                elif s.startswith('*/',self.i): depth-=1; self.i+=2
                else: self.i+=1
            self.emit('DOCUMENTATION' if s.startswith('/**',a) else 'COMMENT',a,self.i)
            if depth: self.error(4,'Unterminated multiline comment',a,self.i,'Close with */')
            return
        if c in '\"\'' or s.startswith(('raw"','b"'),a): self.string(); return
        if c.isascii() and c.isdigit():
            self.i+=1
            while self.i<n:
                x=s[self.i]
                if x.isalnum() or x=='_': self.i+=1
                elif x=='.' and not s.startswith('..',self.i) and self.i+1<n and s[self.i+1].isdigit(): self.i+=1
                elif x in '+-' and s[self.i-1] in 'eE' and not s[a:self.i].lower().startswith(('0x','0b','0o')): self.i+=1
                else: break
            t=s[a:self.i]; valid=self.number.fullmatch(t)
            self.emit('NUMBER' if valid else 'INVALID',a,self.i)
            if not valid: self.error(10 if '_' in t else 6,'Invalid numeric literal',a,self.i,'Check digits, base and separators')
            return
        if c.isalpha() or c=='_':
            self.i+=1
            while self.i<n and (s[self.i].isalnum() or s[self.i]=='_'): self.i+=1
            t=s[a:self.i]; r=TuxLanguageRegistry
            k='BOOLEAN' if t in ('true','false') else 'NULL' if t=='null' else 'KEYWORD' if t in r.keywords else 'TYPE_IDENTIFIER' if t in r.types else 'BUILTIN' if t in r.builtins else 'CONTEXTUAL' if t in r.contextual else 'IDENTIFIER'
            self.emit(k,a,self.i)
            scripts=set() if t.isascii() else {unicodedata.name(x,'').split(' ')[0] for x in t if x.isalpha()} & {'LATIN','CYRILLIC','GREEK'}
            if len(scripts)>1: self.error(1,'Mixed-script identifier may be confusing',a,self.i,warning=True)
            return
        if c in '()[]{};,': self.i+=1; self.emit({'(':'LEFT_PAREN',')':'RIGHT_PAREN','[':'LEFT_BRACKET',']':'RIGHT_BRACKET','{':'LEFT_BRACE','}':'RIGHT_BRACE',',':'COMMA',';':'SEMICOLON'}[c],a,self.i); return
        for op in self.operator_groups.get(c, ()):
            if s.startswith(op,a): self.i+=len(op); self.emit('OPERATOR',a,self.i); return
        self.i+=1; self.emit('INVALID',a,self.i)
        if unicodedata.category(c)=='Cf': self.error(2,'Suspicious invisible character',a,self.i,warning=True)
        else: self.error(1,'Unexpected character',a,self.i)
    def string(self):
        s=self.s; a=self.i; raw=s.startswith('raw"',a); binary=s.startswith('b"',a); p=a+(3 if raw else 1 if binary else 0); char=s[p]=="'"; q='"""' if s.startswith('"""',p) else s[p]; kind='CHARACTER' if char else 'RAW_STRING' if raw else 'BINARY_STRING' if binary else 'STRING'; self.i=p+len(q); chunk=a; count=0
        while self.i<len(s):
            i=self.i
            if s.startswith(q,i):
                self.i+=len(q); self.emit(kind,chunk,self.i)
                if char and count!=1: self.error(7,'Character literal must contain one code point',a,self.i)
                return
            c=s[i]
            if c=='\n' and len(q)==1: break
            if c=='\\' and not raw:
                if chunk<i: self.emit(kind,chunk,i)
                m=re.match(r'\\(?:[ntr\\"\'0b$]|x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|u\{[0-9a-fA-F]{1,6}\})',s[i:]); self.i=i+(len(m.group()) if m else min(2,len(s)-i)); self.emit('ESCAPE',i,self.i)
                if not m: self.error(9 if s[i+1:i+2]=='u' else 5,'Invalid escape sequence',i,self.i)
                elif m.group().startswith('\\u'):
                    v=int(m.group()[2:].strip('{}'),16)
                    if v>0x10ffff or 0xd800<=v<=0xdfff: self.error(9,'Invalid Unicode scalar',i,self.i)
                chunk=self.i; count+=1; continue
            if not raw and not char and not binary and c in '{}':
                if s.startswith(c*2,i): self.i+=2; continue
                if c=='{':
                    if chunk<i: self.emit(kind,chunk,i)
                    self.i+=1; self.emit('INTERPOLATION_START',i,self.i); depth=0; self.depth+=1
                    while self.i<len(s) and self.depth<64:
                        x=s[self.i]
                        if x=='}' and depth==0: break
                        if x=='{': depth+=1
                        elif x=='}': depth-=1
                        self.scan()
                    self.depth-=1
                    if self.i<len(s) and s[self.i]=='}': self.emit('INTERPOLATION_END',self.i,self.i+1); self.i+=1; chunk=self.i; continue
                    self.error(8,'Unterminated or excessively nested interpolation',i,self.i,'Close with }'); return
                self.error(8,'Unmatched interpolation brace',i,i+1,'Use }} for a literal brace')
            self.i+=1; count+=1
        if chunk<self.i: self.emit(kind,chunk,self.i)
        self.error(3 if char else 2,'Unterminated character literal' if char else 'Unterminated string',a,self.i,'Close with '+q)


@dataclass(frozen=True)
class TuxAstNode:
    kind: str
    start: int
    end: int
    value: str = ''
    children: tuple = ()
    node_id: int = 0

@dataclass(frozen=True)
class TuxParseResult:
    root: TuxAstNode
    diagnostics: tuple

class TuxParseError(Exception): pass

class TuxParser:
    precedence = {'**':170,'*':150,'/':150,'//':150,'%':150,'@':150,'+':140,'-':140,'<<':130,'>>':130,'&':120,'^':110,'|':100,'..':90,'..<':90,'==':80,'!=':80,'<':80,'<=':80,'>':80,'>=':80,'in':80,'not in':80,'is':80,'is not':80,'and':60,'xor':50,'or':40,'??':30,'|>':20,'recover':5}
    assignments=set('= += -= *= /= //= %= **= @= &= |= ^= <<= >>= ??='.split())
    def parse(self, source, lex):
        self.source=source; self.ts=[t for t in lex.tokens if t.kind not in ('WHITESPACE','COMMENT','DOCUMENTATION')]; self.i=0; self.uid=0; self.ds=[]; self.depth=0; self.soft=0
        if not self.ts: self.ts=[TuxToken('EOF','',len(source),len(source),1,1)]
        if any('-E-' in d.code for d in lex.diagnostics):
            return TuxParseResult(self.node('Program',0,(),end=len(source)),())
        try: items=self.items('')
        except RecursionError:
            self.error('Parser nesting limit exceeded',raise_error=False); items=[]
        return TuxParseResult(self.node('Program',0,items,end=len(source)),tuple(self.ds))
    def tok(self): return self.ts[min(self.i,len(self.ts)-1)]
    def at(self): return self.tok().text
    def pop(self):
        t=self.tok(); self.i=min(self.i+1,len(self.ts)-1); return t
    def node(self,k,a,children=(),value='',end=None):
        self.uid+=1; return TuxAstNode(k,a,max(a,self.ts[max(0,self.i-1)].end if end is None else end),value,tuple(children),self.uid)
    def error(self,msg,code=1,raise_error=True):
        t=self.tok()
        if len(self.ds)<100: self.ds.append(TuxDiagnostic(f'TUX-E-PAR-{code:03}',msg,t.start,t.end))
        if raise_error: raise TuxParseError(msg)
    def nl(self):
        while self.tok().kind=='NEWLINE': self.pop()
    def accept(self,s):
        if self.at()==s and self.tok().kind!='EOF': return self.pop()
    def need(self,s):
        if not self.accept(s): self.error('Expected '+repr(s),4)
    def name(self):
        t=self.tok()
        if t.kind not in ('IDENTIFIER','TYPE_IDENTIFIER','BUILTIN','CONTEXTUAL'): self.error('Expected identifier')
        self.pop(); return self.node('Identifier',t.start,value=t.text)
    def member_name(self):
        if self.at()=='error':
            t=self.pop(); return self.node('Identifier',t.start,value=t.text)
        return self.name()
    def items(self,end):
        out=[]
        while self.tok().kind!='EOF' and (not end or self.at()!=end):
            if self.at() in ('\n',';'): self.pop(); continue
            start=self.i; a=self.tok().start
            try:
                out.append(self.statement())
                if self.at() not in ('\n',';','}', '') and self.ts[max(0,self.i-1)].text!='}': self.error('Expected statement separator')
            except TuxParseError:
                self.soft=0
                while self.tok().kind!='EOF' and self.at() not in ('\n',';','}'): self.pop()
                if self.i==start and not (end and self.at()==end): self.pop()
                out.append(self.node('ErrorStatement',a))
            if self.i==start and not (end and self.at()==end): self.pop()
        return out
    def block(self):
        self.nl(); a=self.tok().start; self.need('{'); children=self.items('}'); self.need('}'); return self.node('Block',a,children)
    def type_expr(self):
        a=self.tok().start; n=self.name(); children=[n]
        if self.accept('('):
            self.nl()
            while self.at()!=')':
                if self.tok().kind=='NUMBER': children.append(self.expr(0))
                else: children.append(self.type_expr())
                self.nl()
                if not self.accept(','): break
                self.nl()
            self.need(')')
        nullable=bool(self.accept('?')); result=self.node('NullableType' if nullable else 'Type',a,children)
        if self.accept('|'): result=self.node('UnionType',a,[result,self.type_expr()])
        return result
    def object_declaration(self):
        t=self.pop(); kind=t.text; a=t.start; children=[self.name()]
        if self.accept('extends'):
            if kind!='class': self.error('Only classes support inheritance')
            children.append(self.node('BaseType',self.tok().start,[self.type_expr()]))
        self.nl(); self.need('{'); self.nl()
        while self.at()!='}':
            if self.tok().kind=='EOF': self.error('Expected closing object brace',4)
            if self.accept(';'): self.nl(); continue
            start=self.i; m=self.tok().start
            if kind=='enum':
                parts=[self.name()]
                if self.accept('='): parts.append(self.expr())
                children.append(self.node('EnumMember',m,parts))
                if self.accept(','): self.nl(); continue
            else:
                modifiers=[]; seen=set()
                while self.at() in ('public','private','protected','static','override'):
                    mod=self.pop()
                    if mod.text in seen or (mod.text in ('public','private','protected') and seen.intersection(('public','private','protected'))): self.error('Conflicting or duplicate member modifier')
                    seen.add(mod.text); modifiers.append(self.node('MemberModifier',mod.start,value=mod.text))
                if self.at()=='func':
                    fn=self.statement()
                    if any(z.kind=='FunctionAliases' for z in fn.children): self.error('Method aliases are not supported yet')
                    member=self.node('MethodDeclaration',m,[*modifiers,*fn.children])
                elif self.accept('init'):
                    if kind!='class': self.error('Constructor requires a class')
                    if seen.intersection(('static','override')): self.error('Invalid constructor modifier')
                    self.need('('); self.nl(); parts=[]
                    while self.at()!=')':
                        pos=self.tok().start; param=[self.name()]
                        if self.accept('as'): param.append(self.type_expr())
                        if self.accept('='): param.append(self.expr())
                        parts.append(self.node('Parameter',pos,param)); self.nl()
                        if not self.accept(','): break
                        self.nl()
                    self.need(')'); parts.append(self.block()); member=self.node('ConstructorDeclaration',m,[*modifiers,*parts])
                elif self.at() in ('var','const'):
                    field=self.statement(); member=self.node('FieldDeclaration',m,[*modifiers,*field.children],field.kind)
                elif kind in ('record','error'):
                    parts=[self.name()]; self.need('as'); parts.append(self.type_expr())
                    if self.accept('='): parts.append(self.expr())
                    member=self.node('FieldDeclaration',m,[*modifiers,*parts])
                else: self.error('Expected object member declaration')
                children.append(member)
            if self.at() not in ('}', '\n',';') and self.ts[max(0,self.i-1)].text!='}': self.error('Expected member separator')
            self.nl()
            if self.i==start: self.error('Expected object member')
        self.need('}'); return self.node(kind.title()+'Declaration',a,children)
    def attached(self,word):
        save=self.i; self.nl()
        if self.accept(word): return True
        self.i=save; return False
    def permission_block(self,a):
        self.nl(); self.need('{'); self.nl(); children=[]
        while self.at()!='}':
            if self.tok().kind=='EOF': self.error('Expected closing permissions brace',4)
            if self.accept(';'): self.nl(); continue
            pos=self.tok().start; mode='require'
            if self.at() in ('require','optional'): mode=self.pop().text
            capability=self.expr()
            if capability.kind not in ('Call','MemberAccess','Identifier'): self.error('Expected capability expression')
            parts=[capability]
            if self.attached('reason'): parts.append(self.expr())
            children.append(self.node('PermissionEntry',pos,parts,mode))
            if self.at() not in (';', '\n','}'): self.error('Expected permission separator')
            self.nl()
        self.need('}'); return self.node('PermissionDeclaration',a,children)
    def import_item(self):
        a=self.tok().start; parts=[]
        if self.tok().kind in ('STRING','RAW_STRING'): parts.append(self.expr(191))
        else:
            parts.append(self.name())
            while self.accept('.'):
                if self.accept('{'):
                    self.nl(); selections=[self.name()]
                    while self.accept(','):
                        self.nl()
                        if self.at()=='}': break
                        selections.append(self.name())
                    self.nl(); self.need('}'); parts.append(self.node('ImportSelection',selections[0].start,selections)); break
                parts.append(self.name())
        if self.accept('as'): parts.append(self.node('ImportAlias',self.tok().start,[self.name()]))
        if self.accept('with'):
            pos=self.tok().start; self.need('permissions'); parts.append(self.permission_block(pos))
        return self.node('ImportItem',a,parts)
    def statement(self):
        a=self.tok().start; s=self.at()
        if s in ('class','record','enum','error'): return self.object_declaration()
        if s in ('var','const'):
            self.pop(); bindings=[self.name()]
            while self.accept(','): bindings.append(self.name())
            if self.accept('as'): bindings.append(self.type_expr())
            if self.accept('='):
                self.nl(); bindings.append(self.expr())
                while self.accept(','):
                    item=self.expr()
                    if self.accept('='):
                        if item.kind!='Identifier': self.error('Expected declaration name')
                        item=self.node('InitializedBinding',item.start,[item,self.expr()])
                    bindings.append(item)
            elif s=='const': self.error('Constant requires an initializer')
            return self.node('VariableDeclaration' if s=='var' else 'ConstantDeclaration',a,bindings)
        if s=='add':
            self.pop(); children=[self.import_item()]
            while self.accept(','): self.nl(); children.append(self.import_item())
            return self.node('ImportDeclaration',a,children)
        if s=='try':
            self.pop(); children=[self.block()]; catches=0
            while self.attached('catch'):
                pos=self.ts[self.i-1].start; parts=[]
                if self.accept('{'):
                    self.nl(); parts.append(self.type_expr())
                    while self.accept(','): self.nl(); parts.append(self.type_expr())
                    self.nl(); self.need('}')
                else: parts.append(self.type_expr())
                if self.accept('as'): parts.append(self.iter_binding())
                if self.accept('when'): parts.append(self.expr())
                parts.append(self.block()); children.append(self.node('CatchClause',pos,parts)); catches+=1
            if self.attached('else'):
                if not catches: self.error('Try else requires a catch clause')
                children.append(self.node('TryElseClause',self.ts[self.i-1].start,[self.block()]))
            if self.attached('finally'): children.append(self.node('FinallyClause',self.ts[self.i-1].start,[self.block()]))
            elif not catches: self.error('Try requires catch or finally')
            return self.node('TryStatement',a,children)
        if s=='using':
            self.pop(); binding=self.iter_binding(); self.need('='); resource=self.expr()
            return self.node('UsingStatement',a,[binding,resource,self.block()])
        if s=='permissions':
            self.pop(); return self.permission_block(a)
        if s=='limits':
            self.pop(); self.nl(); self.need('{'); self.nl(); children=[]; seen=set()
            while self.at()!='}':
                if self.tok().kind=='EOF': self.error('Expected closing limits brace',4)
                if self.accept(';'): self.nl(); continue
                key=self.name()
                if key.value in seen: self.error('Duplicate resource limit: '+key.value)
                seen.add(key.value); self.need(':'); value=self.expr(); children.append(self.node('LimitEntry',key.start,[key,value]))
                if self.at() not in (';', '\n','}'): self.error('Expected limit separator')
                self.nl()
            self.need('}'); return self.node('LimitDeclaration',a,children)
        if s=='throw':
            self.pop(); children=[]
            if self.at() not in ('\n',';','}',''):
                children.append(self.expr())
                if self.accept('from'): children.append(self.node('ExceptionCause',self.tok().start,[self.expr()]))
            return self.node('ThrowStatement',a,children)
        if s=='func':
            self.pop(); children=[self.name()]; self.need('('); self.nl()
            while self.at()!=')':
                p=self.tok().start; parts=[self.name()]
                if self.accept('as'): parts.append(self.type_expr())
                if self.accept('='): parts.append(self.expr())
                children.append(self.node('Parameter',p,parts)); self.nl()
                if not self.accept(','): break
                self.nl()
            self.need(')')
            if self.accept('as'): children.append(self.type_expr())
            if self.accept('with'):
                pos=self.tok().start; self.need('alias'); self.need('('); self.nl(); aliases=[]; seen={children[0].value}
                while True:
                    token=self.tok(); raw=token.text
                    if token.kind!='STRING' or not raw.startswith('"'): self.error('Alias requires a quoted identifier')
                    # Consume the complete string using the ordinary expression parser.
                    literal=self.expr(); raw=literal.value
                    if literal.kind!='Literal' or not raw.startswith('"') or not raw.endswith('"'): self.error('Alias requires a plain quoted identifier')
                    name=raw[1:-1]
                    if not name.isidentifier() or not (name[0].isalpha() or name[0]=='_') or not all(c.isalnum() or c=='_' for c in name) or name in TuxLanguageRegistry.keywords | TuxLanguageRegistry.builtins | TuxLanguageRegistry.types: self.error('Invalid or reserved function alias: '+name)
                    if name in seen: self.error('Duplicate function alias: '+name)
                    seen.add(name); aliases.append(self.node('Identifier',literal.start,value=name,end=literal.end)); self.nl()
                    if not self.accept(','): break
                    self.nl()
                self.need(')'); children.append(self.node('FunctionAliases',pos,aliases))
            if self.accept('=>'): self.nl(); children.append(self.expr())
            else: children.append(self.block())
            return self.node('FunctionDeclaration',a,children)
        if s in ('if','unless','while','until'):
            self.pop(); children=[self.expr()]
            if self.accept('then'): children.append(self.statement())
            else: children.append(self.block())
            if s=='if':
                save=self.i; self.nl()
                if self.accept('else'): children.append(self.statement() if self.at()=='if' else self.block())
                else: self.i=save
            return self.node(s.title()+'Statement',a,self.loop_clauses(children) if s in ('while','until') else children)
        if s=='for':
            self.pop()
            if self.accept('('):
                init=[]; conditions=[]; updates=[]
                self.nl()
                while self.at()!=';':
                    if self.accept('!'):
                        binding=self.name(); self.need('='); init.append(self.node('TemporaryBinding',binding.start,[binding,self.expr()]))
                    else: init.append(self.statement())
                    if not self.accept(','): break
                self.need(';'); self.nl()
                while self.at()!=';':
                    conditions.append(self.expr())
                    if not self.accept(','): break
                self.need(';'); self.nl()
                while self.at()!=')':
                    update=self.expr()
                    if self.accept('with'):
                        self.need('step'); update=self.node('UpdateStep',update.start,[update,self.expr()])
                    updates.append(update)
                    if not self.accept(','): break
                self.need(')')
                children=[self.node('ForInitializers',a,init),self.node('ForConditions',a,conditions),self.node('ForUpdates',a,updates),self.block()]
                return self.node('ForStatement',a,self.loop_clauses(children))
            children=[self.iter_binding()]
            while self.accept(','): children.append(self.iter_binding())
            self.need('in'); children.append(self.expr())
            seen=set()
            while self.at() in ('step','with','along','where','skip','take'):
                t=self.pop(); mod=t.text
                if mod in seen and mod!='along': self.error('Duplicate iteration modifier: '+mod)
                seen.add(mod)
                if mod=='with':
                    self.need('index'); binding=self.iter_binding(); parts=[binding]
                    if self.accept('('): parts.append(self.expr()); self.need(')')
                    children.append(self.node('IndexBinding',t.start,parts))
                elif mod=='along':
                    binding=self.iter_binding(); self.need('in'); parts=[binding,self.expr()]
                    strict=bool(self.accept('strict')); children.append(self.node('AlongClause',t.start,parts,'strict' if strict else ''))
                else: children.append(self.node(mod.title()+'Clause',t.start,[self.expr()]))
            children.append(self.block()); return self.node('ForEachStatement',a,self.loop_clauses(children))
        if s=='check':
            self.pop(); self.nl(); self.need('{'); self.nl(); branches=[]; otherwise=False
            while self.at()!='}':
                t=self.pop()
                if otherwise: self.error('Otherwise must be the final check branch')
                if t.text=='when': branches.append(self.node('WhenClause',t.start,[self.expr(),self.block()]))
                elif t.text=='otherwise': otherwise=True; branches.append(self.node('OtherwiseClause',t.start,[self.block()]))
                else: self.error('Expected when or otherwise')
                self.nl()
            self.need('}'); return self.node('CheckStatement',a,branches)
        if s=='switch':
            self.pop(); return self.switch_body(a,False)
        if s=='label':
            self.pop(); name=self.name(); self.need(':'); self.nl()
            return self.node('LabelStatement',a,[name,self.statement()])
        if s=='assert':
            self.pop(); children=[self.expr()]
            if self.accept(','): children.append(self.expr())
            return self.node('AssertStatement',a,children)
        if s=='outer':
            self.pop(); children=[self.name()]
            while self.accept(','): children.append(self.name())
            return self.node('OuterStatement',a,children)
        if s=='type' and self.i+2<len(self.ts) and self.ts[self.i+2].text=='=':
            self.pop(); name=self.name(); self.need('=')
            return self.node('TypeAliasDeclaration',a,[name,self.type_expr()])
        if s=='guard':
            self.pop(); condition=self.expr(); self.nl(); self.need('else')
            return self.node('GuardStatement',a,[condition,self.block()])
        if s=='do':
            self.pop(); body=self.block(); self.nl(); self.need('while')
            return self.node('DoWhileStatement',a,[body,self.expr()])
        if s=='repeat':
            self.pop(); self.nl()
            if self.at()=='{':
                body=self.block(); self.nl(); self.need('until')
                return self.node('RepeatUntilStatement',a,[body,self.expr()])
            children=[self.expr()]
            if self.accept('as'):
                self.need('!'); binding=self.name(); parts=[binding]
                if self.accept('('): parts.append(self.expr()); self.need(')')
                children.append(self.node('TemporaryBinding',binding.start,parts))
            children.append(self.block())
            return self.node('RepeatCountStatement',a,self.loop_clauses(children))
        if s=='defer':
            self.pop(); return self.node('DeferStatement',a,[self.block() if self.at()=='{' else self.expr()])
        if s in ('program','forever'):
            self.pop(); return self.node(s.title()+'Statement',a,[self.block()])
        if s in ('return','yield','throw','break','continue'):
            self.pop(); children=[]
            if self.at() not in ('\n',';','}',''): children.append(self.expr())
            return self.node(s.title()+'Statement',a,children)
        if s in ('class','record','enum','error','permissions','limits','switch','try','using','repeat','do','guard','defer','retry','check','label'):
            self.error('Feature not yet supported by parser 0.10.2.1: '+s,90)
        left=self.expr(); targets=[left]
        while self.accept(','): targets.append(self.expr())
        if self.at() in self.assignments:
            op=self.pop().text
            if any(n.kind not in ('Identifier','MemberAccess','Index') for n in targets): self.error('Invalid assignment target',5)
            self.nl(); vals=[self.expr()]
            while self.accept(','): vals.append(self.expr())
            return self.node('AssignmentStatement',a,targets+vals,op)
        if len(targets)>1: self.error('Expected assignment')
        return self.node('ExpressionStatement',a,[left])
    def iter_binding(self):
        a=self.tok().start; self.need('!'); parts=[self.name()]
        if self.accept('as'): parts.append(self.type_expr())
        return self.node('TemporaryBinding',a,parts)
    def loop_clauses(self,children):
        seen=set()
        while True:
            save=self.i; self.nl()
            if self.at() not in ('completed','empty'): self.i=save; break
            t=self.pop()
            if t.text in seen: self.error('Duplicate loop clause: '+t.text)
            seen.add(t.text); children.append(self.node(t.text.title()+'Clause',t.start,[self.block()]))
        return children
    def switch_body(self,a,expression):
        children=[self.expr()]; self.nl(); self.need('{'); self.nl(); default=False
        while self.at()!='}':
            t=self.pop(); parts=[]
            if default: self.error('Default must be the final switch branch')
            if t.text=='case':
                while True:
                    if self.accept('is'): parts.append(self.node('TypePattern',t.start,[self.type_expr()]))
                    else: parts.append(self.expr())
                    if not self.accept(','): break
                if self.accept('when'): parts.append(self.node('CaseGuard',self.tok().start,[self.expr()]))
            elif t.text=='default': default=True
            else: self.error('Expected case or default')
            if expression: self.need('=>'); self.nl(); parts.append(self.expr())
            else: parts.append(self.block())
            children.append(self.node('DefaultClause' if default else 'CaseClause',t.start,parts)); self.nl()
            while self.accept(';'): self.nl()
        self.need('}'); return self.node('SwitchExpression' if expression else 'SwitchStatement',a,children)
    def sequence(self,end):
        children=[]; self.nl()
        while self.at()!=end:
            n=self.expr()
            if self.accept(':'): n=self.node('Pair',n.start,[n,self.expr()])
            children.append(n); self.nl()
            if not self.accept(','): break
            self.nl()
        self.need(end); return children
    def expr(self,minimum=0):
        self.depth+=1
        try:
            if self.depth>100: self.error('Expression nesting limit exceeded')
            return self.expression(minimum)
        finally: self.depth-=1
    def expression(self,minimum):
        t=self.pop(); a=t.start; s=t.text
        if s in ('+','-','~','not','++','--'):
            self.nl(); n=self.expr(70 if s=='not' else 160); left=self.node('UnaryExpression',a,[n],s)
            if s in ('++','--') and n.kind not in ('Identifier','MemberAccess','Index'): self.error('Invalid update target',6)
        elif s=='!' or (s=='(' and (self.at()=='!' or (self.at()==')' and self.i+1<len(self.ts) and self.ts[self.i+1].text=='=>'))):
            params=[]
            if s=='!':
                key=self.name(); params.append(self.node('Parameter',key.start,[key]))
            else:
                self.nl()
                while self.at()!=')':
                    self.need('!'); key=self.name(); parts=[key]
                    if self.accept('as'):parts.append(self.type_expr())
                    params.append(self.node('Parameter',key.start,parts)); self.nl()
                    if not self.accept(','):break
                    self.nl()
                self.need(')')
            self.need('=>'); self.nl(); body=self.expr()
            left=self.node('LambdaExpression',a,[*params,body])
        elif s=='attempt':
            left=self.node('AttemptExpression',a,[self.expr(6)])
        elif s=='switch':
            left=self.switch_body(a,True)
        elif s=='if':
            cond=self.expr(); self.need('then'); yes=self.expr(); self.nl(); self.need('else'); left=self.node('ConditionalExpression',a,[cond,yes,self.expr()])
        elif s in ('(','[','{'):
            end={'(':')','[':']','{':'}'}[s]; first=self.i; self.soft+=1
            try: children=self.sequence(end)
            finally: self.soft-=1
            comma=any(self.ts[j].text==',' for j in range(first,self.i-1)) if s=='(' and len(children)==1 else False
            left=self.node(('GroupExpression' if len(children)==1 and not comma else 'TupleExpression') if s=='(' else 'ListExpression' if s=='[' else 'DictionaryExpression',a,children)
        elif t.kind in ('STRING','RAW_STRING','BINARY_STRING','CHARACTER'):
            children=[]
            while self.tok().kind in ('ESCAPE','STRING','RAW_STRING','BINARY_STRING','CHARACTER','INTERPOLATION_START') and self.tok().start==self.ts[self.i-1].end:
                if self.tok().kind=='INTERPOLATION_START':
                    self.pop(); children.append(self.expr())
                    if self.accept(':'):
                        while self.tok().kind not in ('INTERPOLATION_END','EOF'): self.pop()
                    if self.tok().kind!='INTERPOLATION_END': self.error('Expected interpolation closing brace')
                    self.pop()
                else: self.pop()
            left=self.node('InterpolatedString' if children else 'Literal',a,children,self.source[a:self.ts[self.i-1].end])
        elif t.kind in ('NUMBER','BOOLEAN','NULL'): left=self.node('Literal',a,value=s)
        elif s=='me': left=self.node('MeExpression',a,value=s)
        elif t.kind in ('IDENTIFIER','TYPE_IDENTIFIER','BUILTIN','CONTEXTUAL') or s=='type': left=self.node('Identifier',a,value=s)
        else:
            self.i=max(0,self.i-1) if t.kind!='EOF' else self.i; self.error('Expected expression')
        while True:
            if self.soft: self.nl()
            elif self.at()=='\n':
                save=self.i; self.nl()
                if self.at()!='|>': self.i=save; break
            op=self.at()
            if op in ('(', '[', '.', '?.') and minimum<=190:
                self.pop()
                if op in ('.','?.'): left=self.node('MemberAccess' if op=='.' else 'OptionalMemberAccess',a,[left,self.member_name()],op)
                else:
                    self.soft+=1
                    try: args=self.sequence(')' if op=='(' else ']')
                    finally: self.soft-=1
                    left=self.node('Call' if op=='(' else 'Index',a,[left]+args)
                continue
            if op in ('++','--') and minimum<=180:
                if left.kind not in ('Identifier','MemberAccess','Index'): self.error('Invalid update target',6)
                self.pop(); left=self.node('PostfixUpdate',a,[left],op); continue
            if op in ('is','not') and self.i+1<len(self.ts):
                pair=op+' '+self.ts[self.i+1].text
                if pair in ('is not','not in'): op=pair
            p=self.precedence.get(op,-1)
            if p<minimum: break
            self.pop()
            if ' ' in op: self.pop()
            self.nl(); right=self.type_expr() if op in ('is','is not') else self.expr(p if op in ('**','??','recover') else p+1)
            if op in ('..','..<') and left.kind=='RangeExpression': self.error('Chained range',8)
            if op=='|>' and right.kind!='Call': self.error('Pipeline requires a call',10)
            if p==80:
                if left.kind=='ComparisonChain' and (op in ('in','not in','is','is not') or any(x in left.value.split(',') for x in ('in','not in','is','is not'))): self.error('Invalid comparison chain',12)
                left=self.node('ComparisonChain',a,(*left.children,right) if left.kind=='ComparisonChain' else (left,right),left.value+','+op if left.kind=='ComparisonChain' else op)
            else: left=self.node('RangeExpression' if p==90 else 'PipelineExpression' if op=='|>' else 'BinaryExpression',a,[left,right],op)
        return left


@dataclass(frozen=True)
class TuxSymbol:
    name: str
    type_name: str
    constant: bool
    node_id: int
    depth: int = 0
    start: int = 0
    end: int = 0

class TuxSemanticAnalyzer:
    """Conservative first pass; unsupported constructs are deliberately skipped."""
    def analyze(self, parsed):
        self.diagnostics=[]; self.scopes=[{}]; self.symbols=[]; self.signatures={}; self.returns=[]
        if parsed and not parsed.diagnostics:
            try: self.visit(parsed.root)
            except RecursionError: pass
        return tuple(self.diagnostics)
    def report(self,n,code,msg):
        if len(self.diagnostics)<100: self.diagnostics.append(TuxDiagnostic(f'TUX-E-SEM-{code:03}',msg,n.start,n.end))
    def lookup(self,name):
        return next((s[name] for s in reversed(self.scopes) if name in s),None)
    def declare(self,n,t='any',constant=False):
        if n.value in self.scopes[-1]: self.report(n,2,'Duplicate declaration: '+n.value); return
        s=TuxSymbol(n.value,t,constant,n.node_id,len(self.scopes)-1,n.start,n.end); self.scopes[-1][n.value]=s; self.symbols.append(s)
    def type_name(self,n):
        return n.children[0].value if n.kind=='Type' and len(n.children)==1 else 'any'
    def compatible(self,n,t,v):
        if t in ('int','float','bool','string','char') and v!='any' and t!=v and not (t=='float' and v=='int'):
            self.report(n,4,f'Cannot assign {v} to {t}')
    def expr(self,n):
        k=n.kind; c=n.children; v=n.value
        if k=='BinaryExpression' and v in ('+','-','*','/','//','%','**','and','or','xor'):
            a,b=map(self.expr,c)
            if 'any' in (a,b): return 'any'
            if v in ('and','or','xor'):
                if a==b=='bool': return 'bool'
            elif a in ('int','float') and b in ('int','float'):
                return 'float' if 'float' in (a,b) or v=='/' else 'any' if v=='**' else 'int'
            elif v=='+' and a==b=='string': return 'string'
            elif v=='*' and a=='string' and b=='int': return 'string'
            else: return 'any'
            self.report(n,5,'Boolean operator requires bool operands'); return 'any'
        if k=='GroupExpression' and len(c)==1: return self.expr(c[0])
        if k=='InterpolatedString':
            for x in c: self.expr(x)
            return 'string'
        if k=='LambdaExpression':
            self.scopes.append({})
            try:
                for p in c[:-1]:self.declare(p.children[0],self.type_name(p.children[1]) if len(p.children)>1 else 'any')
                self.expr(c[-1])
            finally:self.scopes.pop()
            return 'any'
        if k=='PipelineExpression':
            call=c[1]
            return self.expr(TuxAstNode('Call',n.start,n.end,children=(call.children[0],c[0],*call.children[1:])))
        if k=='Call' and c[0].kind=='Identifier':
            symbol=self.lookup(c[0].value); sig=self.signatures.get(symbol.node_id) if symbol else None
            if sig and all(x.kind!='Pair' for x in c[1:]):
                params,ret=sig; args=[self.expr(x) for x in c[1:]]
                required=sum(not default for _,default in params)
                if not required<=len(args)<=len(params): self.report(n,6,'Incorrect argument count: '+c[0].value)
                for x,vv,(tt,_) in zip(c[1:],args,params): self.compatible(x,tt,vv)
                return ret
        if k=='Identifier':
            s=self.lookup(v)
            if s: return s.type_name
            if v not in TuxLanguageRegistry.builtins | TuxLanguageRegistry.types | {'Error','ValueError','TypeError','AssertionError','ArithmeticError','DivisionByZeroError','IndexError','LookupError'}: self.report(n,1,'Undeclared identifier: '+v)
        elif k=='Literal':
            if v in ('true','false'): return 'bool'
            if v=='null': return 'null'
            if v.startswith(('"','raw"')): return 'string'
            if v.startswith("'"): return 'char'
            if re.fullmatch(r'[0-9][0-9_]*',v): return 'int'
            if re.fullmatch(r'[0-9][0-9_]*\.[0-9_]+',v): return 'float'
        elif k in ('Call','Index','MemberAccess','OptionalMemberAccess'):
            # Member names and named argument keys are not lexical references.
            for x in (c[:1] if k.endswith('Access') else c): self.expr(x)
        elif k=='Pair':
            self.expr(c[-1])
        elif k in ('BinaryExpression','ComparisonChain','RangeExpression','UnaryExpression','PostfixUpdate','GroupExpression','InterpolatedString','PipelineExpression','ListExpression','TupleExpression'):
            for x in c:
                if x.kind not in ('Type','NullableType','UnionType'): self.expr(x)
            if k=='ComparisonChain': return 'bool'
            if k=='PostfixUpdate' or (k=='UnaryExpression' and v in ('++','--')): self.target(c[0])
        return 'any'
    def target(self,n):
        if n.kind=='Identifier':
            s=self.lookup(n.value)
            if s and s.constant: self.report(n,3,'Cannot reassign constant: '+n.value)
            return s
        return None
    def visit(self,n):
        k=n.kind; c=n.children
        if k in ('Program','Block'):
            if k=='Block': self.scopes.append({})
            # Functions can be referenced before their declaration.
            for x in c:
                if x.kind in ('FunctionDeclaration','ClassDeclaration','RecordDeclaration','EnumDeclaration','ErrorDeclaration','TypeAliasDeclaration'): self.declare(x.children[0])
                if x.kind=='FunctionDeclaration':
                    params=[]
                    for param in (z for z in x.children[1:-1] if z.kind=='Parameter'):
                        parts=param.children[1:]; typed=bool(parts and parts[0].kind in ('Type','NullableType','UnionType'))
                        params.append((self.type_name(parts[0]) if typed else 'any',len(parts)>int(typed)))
                    ret=next((self.type_name(z) for z in x.children[1:-1] if z.kind in ('Type','NullableType','UnionType')),'any')
                    self.signatures[x.children[0].node_id]=(params,ret)
                    for group in (z for z in x.children if z.kind=='FunctionAliases'):
                        for alias in group.children:
                            self.declare(alias,constant=True); self.signatures[alias.node_id]=(params,ret)
                elif x.kind=='ImportDeclaration':
                    for item in x.children:
                        alias=next((z.children[0] for z in item.children if z.kind=='ImportAlias'),None)
                        if alias: self.declare(alias)
                        elif item.children and item.children[0].kind=='Identifier':
                            selection=next((z for z in item.children if z.kind=='ImportSelection'),None)
                            for name in (selection.children if selection else [z for z in item.children if z.kind=='Identifier'][-1:]): self.declare(name)
            for x in c: self.visit(x)
            if k=='Block': self.scopes.pop()
        elif k in ('VariableDeclaration','ConstantDeclaration'):
            # AST lacks binding/value boundaries; use source offsets supplied by caller.
            first=c[0]; t='any'; rest=list(c[1:]); constant=k=='ConstantDeclaration'
            if rest and rest[0].kind in ('Type','NullableType','UnionType'): t=self.type_name(rest.pop(0))
            if rest and self.source[first.end:rest[0].start].strip().startswith(','): return
            if rest and rest[0].kind!='InitializedBinding': self.compatible(rest[0],t,self.expr(rest.pop(0)))
            self.declare(first,t,constant)
            for x in rest:
                if x.kind=='InitializedBinding': self.expr(x.children[1]); self.declare(x.children[0],constant=constant)
        elif k=='AssignmentStatement' and len(c)==2:
            t=self.target(c[0]); v=self.expr(c[1]); self.expr(c[0])
            if t and n.value=='=': self.compatible(c[1],t.type_name,v)
        elif k=='FunctionDeclaration':
            self.scopes.append({})
            for x in c[1:]:
                if x.kind=='Parameter':
                    t=self.type_name(x.children[1]) if len(x.children)>1 else 'any'; self.declare(x.children[0],t)
            ret=self.signatures.get(c[0].node_id,([], 'any'))[1]
            self.returns.append(ret)
            if c[-1].kind=='Block': self.visit(c[-1])
            else: self.compatible(c[-1],ret,self.expr(c[-1]))
            self.returns.pop(); self.scopes.pop()
        elif k in ('IfStatement','UnlessStatement','WhileStatement','UntilStatement','GuardStatement'):
            self.expr(c[0])
            for x in c[1:]: self.visit(x)
        elif k=='ReturnStatement':
            for x in c: self.compatible(x,self.returns[-1] if self.returns else 'any',self.expr(x))
        elif k in ('ExpressionStatement','AssertStatement','YieldStatement'):
            for x in c: self.expr(x)
        elif k=='ProgramStatement': self.visit(c[0])


def tux_ast_export(result):
    # Flat node table avoids recursive JSON encoding for long expression chains.
    nodes=[]; stack=[result.root]
    while stack:
        n=stack.pop()
        nodes.append(dict(id=n.node_id,kind=n.kind,start=n.start,end=n.end,value=n.value,children=[c.node_id for c in n.children]))
        stack.extend(reversed(n.children))
    return dict(schemaVersion='0.1.0',root=result.root.node_id,nodes=nodes,diagnostics=[dict(code=d.code,message=d.message,start=d.start,end=d.end) for d in result.diagnostics])


class TuxRuntimeError(Exception): pass
class TuxHardLimit(TuxRuntimeError): pass
class TuxFault(TuxRuntimeError):
    def __init__(self,name,message):
        self.name=name; self.message=message; self.cause=None
        super().__init__(name+': '+message)
    def matches(self,name):
        parents={'DivisionByZeroError':'ArithmeticError','OverflowError':'ArithmeticError','IndexError':'LookupError','KeyError':'LookupError','AssertionError':'ValueError','FileNotFoundError':'IOError','ConversionError':'TypeError','ModuleNotFoundError':'ModuleError'}
        return name in ('Error',self.name,parents.get(self.name))

class TuxReturn(Exception):
    def __init__(self,value): self.value=value
class TuxBreak(Exception): pass
class TuxContinue(Exception): pass
@dataclass(frozen=True)
class TuxFunction:
    node: TuxAstNode
    scopes: tuple

@dataclass(eq=False)
class TuxClass:
    node: TuxAstNode
    scopes: tuple
    base: object = None

@dataclass(eq=False)
class TuxObject:
    cls: TuxClass
    fields: dict
    def __str__(self): return '<'+self.cls.node.children[0].value+' instance>'

@dataclass(frozen=True)
class TuxErrorType:
    name: str

@dataclass(frozen=True)
class TuxNative:
    name: str
    fn: object
    arity: int
    kinds: tuple = ()

@dataclass(eq=False)
class TuxModule:
    name: str
    exports: dict

class TuxCapabilityRegistry:
    """Fixed restricted profile; no host grants in this release."""
    allowed = frozenset(('compute', 'console.output', 'console.input', 'clock.read', 'workspace.read', 'workspace.write'))
    denied = frozenset(('files.read', 'files.write', 'files.delete', 'files.list', 'files.metadata', 'network.connect', 'network.listen', 'process.run', 'process.shell', 'env.read', 'env.write', 'native.execute', 'secrets.read', 'secrets.write'))
    @classmethod
    def status(cls, name):
        return 'granted' if name in cls.allowed else 'restricted' if name in cls.denied else 'unknown'
    @classmethod
    def require(cls, name):
        if cls.status(name) != 'granted':
            raise TuxFault('PermissionError', 'Capability denied: '+name)
    @classmethod
    def native_capability(cls, name):
        module, _, member = name.partition('.')
        if module in ('files','json','csv'):
            if member in ('write','append'): return 'workspace.write'
            if member in ('read','exists','size'): return 'workspace.read'
            if module=='files' and member=='readHost': return 'compute' # scoped check inside host_read
        if module == 'console': return 'console.output'
        if module == 'time' or (module == 'date' and member == 'today'): return 'clock.read'
        if module in ('math','random','convert','validate','path','json','csv','date','format','text','collections','stats','security'): return 'compute'
        return 'native.execute'

def tux_read_selected_file(path):
    # Linux only: no symlink final component, no blocking on special files.
    if not sys.platform.startswith('linux') or not hasattr(os,'O_NOFOLLOW'):
        raise ValueError('Host file selection is not supported on this platform')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError('Select a regular file')
        with os.fdopen(fd,'rb',closefd=False) as stream:
            data=stream.read(400001)
        if len(data)>400000:raise ValueError('Selected file exceeds byte limit')
        text=data.decode('utf-8-sig')
        if len(text)>100000:raise ValueError('Selected file exceeds character limit')
        return text
    finally:os.close(fd)

class TuxInterpreter:
    """Bounded, deliberately small AST interpreter; no host calls."""
    def __init__(self,source,emit,stop=None,read=None,profile="Restricted",review=None):
        self.profile=profile if profile in ("Restricted","Project","Trusted","Testing") else "Restricted"; self.review=review; self.source=source; self.emit=emit; self.read=read; self.stop=stop or threading.Event(); self.scopes=[{}]; self.steps=0; self.output=0; self.depth=0; self.active_faults=[]; self.defer_frames=[]; self.modules={}; self.rng=random.Random(); self.virtual_files={}; self.host_snapshots={}; self.output_limit=100000; self.depth_limit=40; self.execution_limit=60; self.memory_limit=256; self.deadline=None; self.worker_limits=False
    def host_read(self,key):
        if key not in self.host_snapshots:raise TuxFault('PermissionError','No selected file grant: '+key)
        return self.host_snapshots[key]
    def workspace_path(self,value):
        # Virtual workspace only: never resolve or open a host path.
        if not value or len(value)>1024 or any(c in value for c in ('\\', ':', '\x00')) or value.startswith('/') or '..' in value.split('/'):
            raise TuxFault('PermissionError','Path outside virtual workspace')
        path=posixpath.normpath(value)
        if path=='.':raise TuxFault('ValueError','Expected a file name')
        return path
    def workspace_write(self,path,value):
        TuxCapabilityRegistry.require('workspace.write')
        path=self.workspace_path(path)
        if len(value)>100000 or sum(len(v) for k,v in self.virtual_files.items() if k!=path)+len(value)>1000000 or (path not in self.virtual_files and len(self.virtual_files)>=100):
            raise TuxHardLimit('Virtual workspace limit exceeded')
        self.virtual_files[path]=value
    def workspace_read(self,path):
        TuxCapabilityRegistry.require('workspace.read')
        path=self.workspace_path(path)
        if path not in self.virtual_files:raise TuxFault('FileNotFoundError','Virtual file not found')
        return self.virtual_files[path]
    def structured_check(self,value,depth=0,active=None,budget=None):
        if active is None:active=set();budget=[0]
        budget[0]+=1
        if depth>40 or budget[0]>20000:raise TuxHardLimit('Structured data limit exceeded')
        if self.stop.is_set():raise TuxHardLimit('Execution stopped')
        t=type(value)
        if t is int and value.bit_length()>4096:raise TuxHardLimit('Integer limit exceeded')
        if t is float and not math.isfinite(value):raise ValueError('Non-finite number')
        if t is str:
            if len(value)>100000:raise TuxHardLimit('String limit exceeded')
            value.encode('utf-8')
        elif t in (list,tuple,dict):
            if len(value)>10000 or id(value) in active:raise ValueError('Oversized or cyclic collection')
            active.add(id(value))
            try:
                if t is dict:
                    for k,v in value.items():
                        if type(k) is not str:raise TypeError('JSON keys must be strings')
                        self.structured_check(k,depth+1,active,budget);self.structured_check(v,depth+1,active,budget)
                else:
                    for v in value:self.structured_check(v,depth+1,active,budget)
            finally:active.remove(id(value))
        elif t not in (int,float,bool,type(None)):raise TypeError('Unsupported structured value')
    def json_parse(self,text):
        if len(text)>100000:raise TuxHardLimit('String limit exceeded')
        def pairs(items):
            out={}
            for k,v in items:
                if k in out:raise ValueError('Duplicate JSON key')
                out[k]=v
            return out
        def invalid(v):raise ValueError('Invalid JSON constant: '+v)
        try:value=json.loads(text,object_pairs_hook=pairs,parse_constant=invalid)
        except RecursionError:raise TuxHardLimit('Structured data limit exceeded') from None
        self.structured_check(value);return value
    def json_stringify(self,value):
        self.structured_check(value)
        parts=[];size=0
        for part in json.JSONEncoder(ensure_ascii=False,allow_nan=False,separators=(',',':')).iterencode(value):
            if self.stop.is_set():raise TuxHardLimit('Execution stopped')
            size+=len(part)
            if size>100000:raise TuxHardLimit('String limit exceeded')
            parts.append(part)
        return ''.join(parts)
    def csv_parse(self,text):
        if len(text)>100000:raise TuxHardLimit('String limit exceeded')
        rows=[];cells=0
        try:
            for row in csv.reader(io.StringIO(text,newline=''),strict=True):
                if self.stop.is_set():raise TuxHardLimit('Execution stopped')
                cells+=len(row)
                if len(rows)>=10000 or cells>20000 or len(row)>10000:raise TuxHardLimit('Structured data limit exceeded')
                rows.append(row)
        except csv.Error as e:raise ValueError(str(e)) from None
        return rows
    def csv_stringify(self,rows):
        out=io.StringIO(newline='');writer=csv.writer(out,lineterminator='\r\n');cells=0
        for row in rows:
            if self.stop.is_set():raise TuxHardLimit('Execution stopped')
            if type(row) not in (list,tuple) or any(type(v) not in (str,int,float,bool,type(None)) for v in row):raise TypeError('Expected rows of primitive values')
            cells+=len(row)
            if cells>20000:raise TuxHardLimit('Structured data limit exceeded')
            values=[self.fmt(v) for v in row]
            if sum(len(v) for v in values)>100000:raise TuxHardLimit('String limit exceeded')
            writer.writerow(values)
            if out.tell()>100000:raise TuxHardLimit('String limit exceeded')
        return out.getvalue()
    def load_module(self,n,name):
        if name in self.modules:return self.modules[name]
        exports={}
        numeric=(int,float)
        def register(key,fn,*kinds):
            exports[key]=TuxNative(name+'.'+key,fn,len(kinds),kinds)
        if name=='security':
            register('status',TuxCapabilityRegistry.status,(str,))
            register('has',lambda v:TuxCapabilityRegistry.status(v)=='granted',(str,))
            register('require',TuxCapabilityRegistry.require,(str,))
            register('profile',lambda:self.profile)
        elif name=='math':
            exports.update({k:getattr(math,k.lower()) for k in ('PI','E','TAU')})
            exports['PHI']=(1+math.sqrt(5))/2
            for key in ('sqrt','sin','cos','tan','floor','ceil','log','log10','exp','asin','acos','atan','degrees','radians','trunc'):
                register(key,getattr(math,key),numeric)
            for key in ('atan2','hypot'):
                register(key,getattr(math,key),numeric,numeric)
            register('abs',abs,numeric)
            register('gcd',math.gcd,(int,),(int,))
        elif name=='random':
            register('seed',self.rng.seed,(int,))
            register('int',self.rng.randint,(int,),(int,))
            register('float',self.rng.random)
            register('choice',self.rng.choice,(list,tuple,str))
        elif name=='convert':
            def boolean(v):
                if type(v) is bool:return v
                if type(v) is str and v.lower() in ('true','false'):return v.lower()=='true'
                raise ValueError('Expected true or false')
            register('int',int,(int,float,str))
            register('float',float,(int,float,str))
            register('bool',boolean,(bool,str))
            register('string',self.fmt,(int,float,str,bool,type(None)))
        elif name=='validate':
            register('isNumeric',lambda v:type(v) in numeric or (type(v) is str and bool(re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?',v))), (int,float,str,bool,type(None)))
            register('isAlphabetic',str.isalpha,(str,))
            register('isAlphanumeric',str.isalnum,(str,))
            register('isEmpty',lambda v:len(v)==0,(str,list,tuple,dict))
        elif name=='path':
            register('join',posixpath.join,(str,),(str,))
            register('normalize',posixpath.normpath,(str,))
            register('name',posixpath.basename,(str,))
            register('parent',posixpath.dirname,(str,))
            register('stem',lambda v:posixpath.splitext(posixpath.basename(v))[0],(str,))
            register('extension',lambda v:posixpath.splitext(v)[1],(str,))
        elif name=='files':
            register('write',self.workspace_write,(str,),(str,))
            register('read',self.workspace_read,(str,))
            register('readHost',self.host_read,(str,))
            register('exists',lambda p:self.workspace_path(p) in self.virtual_files,(str,))
            register('size',lambda p:len(self.workspace_read(p).encode('utf-8')),(str,))
            register('append',lambda p,v:self.workspace_write(p,self.virtual_files.get(self.workspace_path(p),'')+v),(str,),(str,))
        elif name=='json':
            values=(str,int,float,bool,type(None),list,tuple,dict)
            register('parse',self.json_parse,(str,))
            register('stringify',self.json_stringify,values)
            register('read',lambda p:self.json_parse(self.workspace_read(p)),(str,))
            register('write',lambda p,v:self.workspace_write(p,self.json_stringify(v)),(str,),values)
        elif name=='csv':
            register('parse',self.csv_parse,(str,))
            register('stringify',self.csv_stringify,(list,tuple))
            register('read',lambda p:self.csv_parse(self.workspace_read(p)),(str,))
            register('write',lambda p,v:self.workspace_write(p,self.csv_stringify(v)),(str,),(list,tuple))
        elif name=='date':
            def parse_date(value):
                if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',value):raise ValueError('Expected YYYY-MM-DD')
                return datetime.date.fromisoformat(value)
            register('today',lambda:datetime.date.today().isoformat())
            register('create',lambda y,m,d:datetime.date(y,m,d).isoformat(),(int,),(int,),(int,))
            register('addDays',lambda v,d:(parse_date(v)+datetime.timedelta(days=d)).isoformat(),(str,),(int,))
            register('daysBetween',lambda a,b:(parse_date(b)-parse_date(a)).days,(str,),(str,))
            register('weekday',lambda v:parse_date(v).isoweekday(),(str,))
            register('isLeapYear',lambda y:1<=y<=9999 and y%4==0 and (y%100!=0 or y%400==0),(int,))
        elif name=='time':
            register('timestamp',time.time)
            register('monotonic',time.monotonic)
            register('now',lambda:datetime.datetime.now().astimezone().isoformat(timespec='seconds'))
            register('elapsed',lambda start:time.monotonic()-start,numeric)
        elif name=='format':
            def precision(v,d,kind):
                if not 0<=d<=28:raise ValueError('Precision must be between 0 and 28')
                return format(v,'.'+str(d)+kind)
            register('decimal',lambda v,d:precision(v,d,'f'),numeric,(int,))
            register('percent',lambda v,d:precision(v,d,'%'),numeric,(int,))
            register('group',lambda v:format(v,','),numeric)
            register('hex',lambda v:format(v,'x'),(int,))
            register('binary',lambda v:format(v,'b'),(int,))
        elif name=='console':
            register('write',lambda v:self.output_text(v),(str,))
            register('newline',lambda n:self.newlines(n),(int,))
        elif name=='text':
            register('upp',str.upper,(str,))
            register('low',str.lower,(str,))
            register('trim',str.strip,(str,))
            register('contains',lambda s,t:t in s,(str,),(str,))
            register('wordCount',lambda s:len(s.split()),(str,))
            register('split',lambda s,sep:s.split(sep,10000),(str,),(str,))
            def join(sep,values):
                if any(type(v) is not str for v in values):raise TypeError('Expected strings')
                if sum(map(len,values))+max(0,len(values)-1)*len(sep)>100000:raise TuxHardLimit('String limit exceeded')
                return sep.join(values)
            register('join',join,(str,),(list,tuple))
        elif name in ('collections','stats'):
            seq=(list,tuple)
            def numbers(values):
                if any(type(v) not in numeric for v in values):raise TypeError('Expected numeric elements')
                return values
            if name=='collections':
                register('sorted',lambda v:sorted(numbers(v)),seq)
                register('reversed',lambda v:list(reversed(v)),seq)
                register('sum',lambda v:sum(numbers(v)),seq)
                register('min',lambda v:min(numbers(v)),seq)
                register('max',lambda v:max(numbers(v)),seq)
            else:
                register('avg',lambda v:statistics.mean(numbers(v)),seq)
                register('median',lambda v:statistics.median(numbers(v)),seq)
                def frequency(values):
                    out={}
                    for v in values:
                        if type(v) not in (str,int,float):raise TypeError('Expected string or numeric elements')
                        out[v]=out.get(v,0)+1
                    return out
                register('frequency',frequency,seq)
        else:raise TuxFault('ModuleNotFoundError','Unavailable module: '+name)
        module=TuxModule(name,exports);self.modules[name]=module;return module
    def import_modules(self,n):
        for item in n.children:
            parts=list(item.children)
            if not parts or parts[0].kind!='Identifier' or any(x.kind=='PermissionDeclaration' for x in parts):self.fail(item,'Only registered standard modules are supported')
            module=self.load_module(item,parts[0].value)
            alias=next((x.children[0] for x in parts if x.kind=='ImportAlias'),None)
            selection=next((x for x in parts if x.kind=='ImportSelection'),None)
            names=[x for x in parts[1:] if x.kind=='Identifier']
            if selection:
                if alias or names:self.fail(item,'Unsupported import selection')
                pending=[(key,self.module_member(key,module,key.value)) for key in selection.children]
                keys=[key.value for key,_ in pending]
                if len(set(keys))!=len(keys) or any(key in self.scopes[-1] for key in keys):self.fail(item,'Duplicate import binding')
                for key,value in pending:self.bind(key,value,True)
            elif names:
                if len(names)!=1:self.fail(item,'Unsupported module path')
                self.bind(alias or names[0],self.module_member(names[0],module,names[0].value),True)
            else:self.bind(alias or parts[0],module,True)
    def module_member(self,n,module,key):
        if key not in module.exports:raise TuxFault('ModuleError','Unknown export: '+module.name+'.'+key)
        return module.exports[key]
    def native_call(self,n,fn,args,named):
        if named or len(args)!=fn.arity or any(type(x) not in k for x,k in zip(args,fn.kinds)):raise TuxFault('TypeError',fn.name+' received invalid arguments')
        self.tick(n)
        TuxCapabilityRegistry.require(TuxCapabilityRegistry.native_capability(fn.name))
        try:value=self.guarded(lambda:fn.fn(*args))
        except TuxFault as fault:
            if fn.name.startswith('convert.') and fault.name in ('ValueError','OverflowError'):raise TuxFault('ConversionError',str(fault)) from None
            raise
        if self.stop.is_set():raise TuxHardLimit('Execution stopped')
        if type(value) is float and not math.isfinite(value):raise TuxFault('ValueError','Non-finite math result')
        if type(value) is int and value.bit_length()>4096:self.fail(n,'Integer limit exceeded')
        if type(value) is str and len(value)>100000:self.fail(n,'String limit exceeded')
        if type(value) in (list,tuple,dict) and len(value)>10000:raise TuxHardLimit('Collection limit exceeded')
        return value
    def tick(self,n):
        self.steps+=1
        if self.deadline is not None and time.monotonic()>=self.deadline: raise TuxHardLimit("Execution time limit exceeded")
        if self.stop.is_set(): raise TuxHardLimit('Execution stopped')
        if self.steps>100000: raise TuxHardLimit('Execution step limit exceeded')
    def fail(self,n,msg):
        text=f'Line {self.source.count(chr(10),0,n.start)+1}: {msg}'
        if 'limit exceeded' in msg or msg=='Invalid string repetition': raise TuxHardLimit(text)
        raise TuxFault('AssertionError' if msg=='Assertion failed' else 'Error',text)
    def guarded(self,fn):
        try:return fn()
        except (ZeroDivisionError,OverflowError,IndexError,KeyError,TypeError,ValueError) as e:
            name='DivisionByZeroError' if isinstance(e,ZeroDivisionError) else 'ValueError' if isinstance(e,ValueError) else type(e).__name__
            raise TuxFault(name,str(e)) from None
    def try_statement(self,n):
        c=n.children
        final=next((x for x in c if x.kind=='FinallyClause'),None)
        otherwise=next((x for x in c if x.kind=='TryElseClause'),None)
        try:
            try:self.guarded(lambda:self.stmt(c[0]))
            except TuxFault as fault:
                for clause in (x for x in c if x.kind=='CatchClause'):
                    parts=list(clause.children[:-1]); types=[]
                    while parts and parts[0].kind=='Type':types.append(self.typename(parts.pop(0)))
                    if not any(fault.matches(t) for t in types):continue
                    self.scopes.append({})
                    self.active_faults.append(fault)
                    try:
                        if parts and parts[0].kind=='TemporaryBinding':self.bind(parts.pop(0).children[0],fault,True)
                        if parts and not self.truth(parts[0]):continue
                        self.stmt(clause.children[-1]);break
                    finally:self.active_faults.pop();self.scopes.pop()
                else:raise
            else:
                if otherwise:self.stmt(otherwise.children[0])
        except TuxHardLimit:
            raise
        finally:
            # Do not run user cleanup after cancellation or exhausted hard budget.
            import sys
            if final and not isinstance(sys.exc_info()[1],TuxHardLimit):self.stmt(final.children[0])

    def lookup(self,n):
        for s in reversed(self.scopes):
            if n.value in s: return s[n.value]
        self.fail(n,'Unknown identifier: '+n.value)
    def bind(self,n,v,const=False,t='any'):
        if n.value in self.scopes[-1]: self.fail(n,'Duplicate binding')
        self.scopes[-1][n.value]=[self.convert(n,v,t),const,t]
    def convert(self,n,v,t):
        if isinstance(v,TuxObject):
            cls=v.cls
            while cls:
                if cls.node.children[0].value==t:return v
                cls=cls.base
        if t=='float' and type(v) is int: return float(v)
        if t in ('list','tuple','dict','range') and type(v) is {'list':list,'tuple':tuple,'dict':dict,'range':range}[t]: return v
        if t=='any' or {'int':int,'float':float,'bool':bool,'string':str}.get(t) is type(v): return v
        self.fail(n,'Unsupported or incompatible type: '+t)
    def typename(self,n):
        if n.kind=='Type' and len(n.children)==1: return n.children[0].value
        self.fail(n,'Unsupported type')
    def truth(self,n):
        v=self.expr(n)
        if type(v) is not bool: self.fail(n,'Condition must be bool')
        return v
    def fmt(self,v):
        if v is None:return 'null'
        if type(v) is bool:return 'true' if v else 'false'
        return str(v)
    def binary(self,n,op,a,b):
        import operator
        if op in ('and','or','xor'):
            if type(a) is not bool or type(b) is not bool:self.fail(n,'Boolean operands required')
            return {'and':operator.and_,'or':operator.or_,'xor':operator.xor}[op](a,b)
        if op=='+' and type(a) is type(b) is str:
            if len(a)+len(b)>100000:self.fail(n,'String limit exceeded')
            return a+b
        if op=='*' and type(a) is str and type(b) is int:
            if b<0:raise TuxFault('ValueError','Negative string repetition')
            if len(a)*b>100000:self.fail(n,'String limit exceeded')
            return a*b
        if type(a) not in (int,float) or type(b) not in (int,float):self.fail(n,'Numeric operands required')
        if op=='**' and (abs(b)>1000 or abs(a)>10**100):self.fail(n,'Exponent limit exceeded')
        ops={'+':operator.add,'-':operator.sub,'*':operator.mul,'/':operator.truediv,'//':operator.floordiv,'%':operator.mod,'**':operator.pow}
        if op not in ops:self.fail(n,'Unsupported operator: '+op)
        v=ops[op](a,b)
        if type(v) is int and v.bit_length()>4096:self.fail(n,'Integer limit exceeded')
        if type(v) is float and not math.isfinite(v):self.fail(n,'Non-finite result')
        if type(v) not in (int,float):self.fail(n,'Unsupported numeric result')
        return v
    def decode_text(self,text):
        escapes={'n':'\n','t':'\t','r':'\r','0':'\0','b':'\b','\\':'\\','"':'"',"'":"'",'$':'$'}
        def sub(m):
            x=m.group()[1:]
            return chr(int(x[1:].strip('{}'),16)) if x[0] in 'xu' else escapes[x]
        return re.sub(r'\\(?:u\{[0-9a-fA-F]+\}|u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)',sub,text).replace('{{','{').replace('}}','}')
    def string_value(self,n):
        v=n.value; raw=v.startswith('raw"'); q=3 if v.startswith('"""') or v.startswith('raw"""') else 1
        start=n.start+(3 if raw else 0)+q; end=n.start+len(v)-q
        if raw:return self.source[start:end]
        tokens=TuxLexer().lex(v).tokens; pairs=[]; depth=0
        for t in tokens:
            if t.kind=='INTERPOLATION_START':
                if depth==0: opening=t.start+n.start
                depth+=1
            elif t.kind=='INTERPOLATION_END':
                depth-=1
                if depth==0:pairs.append((opening,t.start+n.start,t.end+n.start))
        out=[]; pos=start
        for child,(opening,closing,after) in zip(n.children,pairs):
            out.append(self.decode_text(self.source[pos:opening])); val=self.expr(child)
            spec=self.source[child.end:closing].strip()
            if spec.startswith(':'):
                spec=spec[1:].strip(); m=re.fullmatch(r'decimal\((\d+)\)',spec)
                if m and int(m[1])<=28 and type(val) in (int,float): val=format(val,'.'+m[1]+'f')
                elif spec=='upper':val=self.fmt(val).upper()
                elif spec=='lower':val=self.fmt(val).lower()
                else:self.fail(n,'Unsupported interpolation format: '+spec)
            out.append(self.fmt(val)); pos=after
        out.append(self.decode_text(self.source[pos:end])); result=''.join(out)
        if len(result)>100000:self.fail(n,'String limit exceeded')
        return result
    def output_text(self,text):
        TuxCapabilityRegistry.require("console.output")
        self.output+=len(text.encode("utf-8"))
        if self.output>self.output_limit:raise TuxHardLimit('Output limit exceeded')
        self.emit(text)
    def newlines(self,count):
        if not 0<=count<=100000:raise TuxFault('ValueError','Invalid newline count')
        self.output_text('\n'*count)
    def input_value(self,n,args,mode='input'):
        TuxCapabilityRegistry.require('console.input')
        if self.read is None:self.fail(n,'Input unavailable')
        if len(args)>1 or (args and type(args[0]) is not str):self.fail(n,'Expected an optional string prompt')
        prompt=args[0] if args else ''
        value=self.read(prompt if mode=='input' else (mode,prompt))
        if self.stop.is_set():raise TuxHardLimit('Execution stopped')
        if type(value) is not str:raise TuxFault('TypeError','Invalid input response')
        if len(value)>100000:self.fail(n,'Input limit exceeded')
        if mode=='confirm':
            if value not in ('true','false'):raise TuxFault('ValueError','Invalid confirmation')
            return value=='true'
        return value
    def expr(self,n):
        self.tick(n); k=n.kind;c=n.children;v=n.value
        if k=='Literal':
            if v in ('true','false','null'):return {'true':True,'false':False,'null':None}[v]
            if v.startswith(('"','raw"')):return self.string_value(n)
            if len(v)>1200:self.fail(n,'Literal limit exceeded')
            try:
                value=int(v.replace('_',''),0) if v.lower().startswith(('0x','0b','0o')) else float(v.replace('_','')) if any(x in v.lower() for x in '.e') else int(v.replace('_',''))
                if type(value) is float and not math.isfinite(value):self.fail(n,'Non-finite literal')
                if type(value) is int and value.bit_length()>4096:self.fail(n,'Integer limit exceeded')
                return value
            except ValueError:self.fail(n,'Unsupported literal')
        if k=='InterpolatedString':return self.string_value(n)
        if k=='LambdaExpression':return TuxFunction(n,tuple(self.scopes))
        if k=='MeExpression':return self.lookup(TuxAstNode('Identifier',n.start,n.end,'me'))[0]
        if k=='Identifier':return self.lookup(n)[0]
        if k in ('ListExpression','TupleExpression'):
            if len(c)>10000:self.fail(n,'Collection limit exceeded')
            values=[self.expr(x) for x in c]
            return values if k=='ListExpression' else tuple(values)
        if k=='DictionaryExpression':
            result={}
            for pair in c:
                if pair.kind!='Pair':self.fail(pair,'Expected dictionary key and value')
                key=self.expr(pair.children[0])
                if key in result:self.fail(pair,'Duplicate dictionary key')
                result[key]=self.expr(pair.children[1])
            return result
        if k=='RangeExpression':return self.make_range(n)
        if k=='Index':
            obj=self.expr(c[0])
            if len(c)!=2 or type(obj) not in (list,tuple,str,range):self.fail(n,'Unsupported indexing')
            i=self.expr(c[1])
            if type(i) is not int:self.fail(n,'Index must be int')
            return obj[i]
        if k=='MemberAccess':
            obj=self.expr(c[0]); key=c[1].value
            if isinstance(obj,TuxFault) and key in ('name','message','cause'):return getattr(obj,key)
            if isinstance(obj,TuxModule):return self.module_member(n,obj,key)
            if isinstance(obj,TuxObject):return self.object_member(n,obj,key)
            if type(obj) is dict and key in obj:return obj[key]
            self.fail(n,'Unknown member: '+key)
        if k=='Call' and c[0].kind=='MemberAccess':
            target=c[0]; obj=self.expr(target.children[0]); name=target.children[1].value
            if isinstance(obj,TuxModule):return self.call_value(n,resolved=self.module_member(n,obj,name))
            if isinstance(obj,TuxObject):return self.call_value(n, resolved=self.object_member(n,obj,name))
            args=[self.expr(x) for x in c[1:]]
            if name=='len' and not args and type(obj) in (list,tuple,dict,range,str):return len(obj)
            if type(obj) is str:
                methods={'upp':(0,str.upper),'low':(0,str.lower),'cap':(0,str.capitalize),'trim':(0,str.strip),'trimS':(0,str.lstrip),'trimE':(0,str.rstrip),'contains':(1,lambda a,b:b in a),'startsWith':(1,str.startswith),'endsWith':(1,str.endswith),'find':(1,str.find),'replace':(2,str.replace),'replaceF':(2,lambda a,b,c:a.replace(b,c,1))}
                if name in methods:
                    count,fn=methods[name]
                    if len(args)!=count or any(type(x) is not str for x in args):self.fail(n,'Invalid string method arguments')
                    if name in ('replace','replaceF') and len(obj)+(len(obj)+1)*len(args[1])>100000:self.fail(n,'String limit exceeded')
                    result=fn(obj,*args)
                    if type(result) is str and len(result)>100000:self.fail(n,'String limit exceeded')
                    return result
            if type(obj) is list and name=='append'  and len(args)==1:
                if len(obj)>=10000:self.fail(n,'Collection limit exceeded')
                if type(args[0]) in (list,dict,tuple):self.fail(n,'Nested mutable insertion not yet supported')
                obj.append(args[0]);return None
            if type(obj) is dict and name=='get' and len(args) in (1,2):return obj.get(*args)
            self.fail(n,'Unsupported collection method: '+name)
        if k=='GroupExpression':return self.expr(c[0])
        if k=='AttemptExpression':
            try:return {'ok':True,'value':self.guarded(lambda:self.expr(c[0])),'error':None}
            except TuxFault as fault:return {'ok':False,'value':None,'error':fault}
        if k=='BinaryExpression':
            if v=='recover':
                try:return self.guarded(lambda:self.expr(c[0]))
                except TuxFault:return self.expr(c[1])
            a=self.expr(c[0])
            if v in ('and','or'):
                if type(a) is not bool:self.fail(n,'Boolean operands required')
                if (v=='and' and not a) or (v=='or' and a):return a
            if v=='??':return a if a is not None else self.expr(c[1])
            return self.binary(n,v,a,self.expr(c[1]))
        if k=='ComparisonChain':
            import operator
            ops={'==':operator.eq,'!=':operator.ne,'<':operator.lt,'>':operator.gt,'<=':operator.le,'>=':operator.ge}
            a=self.expr(c[0])
            for op,x in zip(v.split(','),c[1:]):
                b=self.expr(x)
                if op in ('in','not in'):
                    if type(b) not in (list,tuple,dict,range,str):self.fail(n,'Invalid membership target')
                    return (a in b)==(op=='in')
                if op not in ops:self.fail(n,'Unsupported comparison')
                if type(a)!=type(b) and not (type(a) in (int,float) and type(b) in (int,float)):self.fail(n,'Incompatible comparison')
                if not ops[op](a,b):return False
                a=b
            return True
        if k=='UnaryExpression' and v in ('+','-','not'):
            a=self.expr(c[0])
            if v=='not':
                if type(a) is not bool:self.fail(n,'Boolean operand required')
                return not a
            if type(a) not in (int,float):self.fail(n,'Numeric operand required')
            return -a if v=='-' else a
        if k=='ConditionalExpression':return self.expr(c[1] if self.truth(c[0]) else c[2])
        if k=='PipelineExpression':
            value=self.expr(c[0]); call=c[1]
            return self.call_value(call, [value])
        if k=='Call':return self.call_value(n)
        self.fail(n,'Unsupported expression: '+k)
    def call_value(self,n,prefix=None,resolved=None):
        c=n.children; target=c[0]; args=list(prefix or []); named={}
        for x in c[1:]:
            if x.kind=='Pair':
                key=x.children[0]
                if key.kind!='Identifier' or key.value in named:self.fail(x,'Invalid or duplicate named argument')
                named[key.value]=self.expr(x.children[1])
            else:
                if named:self.fail(x,'Positional argument after named argument')
                args.append(self.expr(x))
        name=target.value if target.kind=='Identifier' else ''
        if name in ('Error','ValueError','TypeError','AssertionError','ArithmeticError','DivisionByZeroError','IndexError','LookupError') and not any(name in scope for scope in self.scopes):
            if named or len(args)!=1 or type(args[0]) is not str:self.fail(n,'Error constructor expects one string')
            return TuxFault(name,args[0])
        if name in ('input','inputPassword','confirm','display','write','newline','displayError','displayWarning','displaySuccess','displayInfo') and not any(name in scope for scope in self.scopes):
            if named:self.fail(n,'Named builtin arguments not supported')
            if name in ('input','inputPassword','confirm'):return self.input_value(n,args,name)
            if name=='newline':
                if len(args)>1 or (args and type(args[0]) is not int):raise TuxFault('TypeError','Expected optional integer count')
                return self.newlines(args[0] if args else 1)
            prefix={'displayError':'[Error] ','displayWarning':'[Warning] ','displaySuccess':'[Success] ','displayInfo':'[Info] '}.get(name,'')
            return self.output_text(prefix+' '.join(map(self.fmt,args))+('' if name=='write' else '\n'))
        fn=resolved if resolved is not None else self.expr(target)
        if isinstance(fn,TuxNative):return self.native_call(n,fn,args,named)
        if isinstance(fn,TuxErrorType):
            if named or len(args)!=1 or type(args[0]) is not str:self.fail(n,'Error constructor expects one string')
            return TuxFault(fn.name,args[0])
        if isinstance(fn,TuxClass):return self.construct(n,fn,args,named)
        return self.invoke(n,fn,args,named)
    def invoke(self,n,fn,args,named):
        if not isinstance(fn,TuxFunction):self.fail(n,'Not a function')
        node=fn.node; params=[x for x in node.children if x.kind=='Parameter']
        if len(args)>len(params):self.fail(n,'Too many arguments')
        if self.depth>=self.depth_limit:self.fail(n,'Call depth limit exceeded')
        old=self.scopes; self.scopes=[*fn.scopes,{}]; self.depth+=1
        try:
            for i,p in enumerate(params):
                key=p.children[0]; parts=list(p.children[1:]); t='any'
                if parts and parts[0].kind in ('Type','NullableType','UnionType'):t=self.typename(parts.pop(0))
                if i<len(args):
                    if key.value in named:self.fail(n,'Duplicate argument: '+key.value)
                    value=args[i]
                elif key.value in named:value=named.pop(key.value)
                elif parts:value=self.expr(parts[0])
                else:self.fail(n,'Missing argument: '+key.value)
                self.bind(key,value,t=t)
            if named:self.fail(n,'Unknown named argument: '+next(iter(named)))
            body=node.children[-1]
            try:
                if body.kind=='Block':self.stmt(body); result=None
                else:result=self.expr(body)
            except TuxReturn as r:result=r.value
            ret=next((x for x in node.children[:-1] if x.kind=='Type'),None)
            return self.convert(n,result,self.typename(ret)) if ret else result
        finally:self.scopes=old;self.depth-=1
    def members(self,cls):
        if cls.base:yield from self.members(cls.base)
        for m in cls.node.children[1:]:
            if m.kind!='BaseType':yield cls,m
    def member_parts(self,m):
        return [x for x in m.children if x.kind!='MemberModifier']
    def bound_method(self,obj,cls,m):
        return TuxFunction(m,(*cls.scopes,{'me':[obj,True,'any']}))
    def object_member(self,n,obj,key):
        if key in obj.fields:return obj.fields[key][0]
        for cls,m in reversed(list(self.members(obj.cls))):
            if m.kind=='MethodDeclaration' and self.member_parts(m)[0].value==key:return self.bound_method(obj,cls,m)
        self.fail(n,'Unknown object member: '+key)
    def construct(self,n,cls,args,named):
        obj=TuxObject(cls,{})
        ctor=None; old=self.scopes
        try:
            for owner,m in self.members(cls):
                self.tick(m); parts=self.member_parts(m)
                self.scopes=[*owner.scopes,{'me':[obj,True,'any']}]
                if m.kind=='FieldDeclaration':
                    key=parts.pop(0); t='any'
                    if parts and parts[0].kind=='Type':t=self.typename(parts.pop(0))
                    if len(parts)>1 or key.value in obj.fields:self.fail(m,'Unsupported or duplicate field')
                    v=self.expr(parts[0]) if parts else {'int':0,'float':0.0,'bool':False,'string':''}.get(t)
                    obj.fields[key.value]=[self.convert(m,v,t),m.value=='ConstantDeclaration',t]
                elif m.kind=='ConstructorDeclaration':ctor=(owner,m)
        finally:self.scopes=old
        if ctor:self.invoke(n,self.bound_method(obj,*ctor),args,named)
        elif args or named:self.fail(n,'Constructor takes no arguments')
        return obj
    def declare_object(self,n):
        c=n.children; base=None
        for m in c[1:]:
            if m.kind=='BaseType':
                name=self.typename(m.children[0]);base=self.lookup(TuxAstNode('Identifier',m.start,m.end,name))[0]
                if not isinstance(base,TuxClass) or base.node.kind!='ClassDeclaration':self.fail(m,'Invalid base class')
            if any(x.kind=='MemberModifier' and x.value not in ('public','override') for x in m.children):self.fail(m,'Unsupported member modifier')
        if n.kind=='EnumDeclaration':
            values={};v=0
            for m in c[1:]:
                key=m.children[0].value
                if key in values:self.fail(m,'Duplicate enum member')
                if len(m.children)>1:v=self.expr(m.children[1])
                if type(v) is not int:self.fail(m,'Enum requires integer values')
                values[key]=v;v+=1
            self.bind(c[0],values,True);return
        if base:
            inherited={self.member_parts(m)[0].value for _,m in self.members(base) if m.kind=='MethodDeclaration'}
            for m in c[1:]:
                if m.kind=='MethodDeclaration':
                    override=any(x.kind=='MemberModifier' and x.value=='override' for x in m.children)
                    if override!=(self.member_parts(m)[0].value in inherited):self.fail(m,'Invalid or missing override')
        self.bind(c[0],TuxClass(n,tuple(self.scopes),base),True)
    def make_range(self,n,step=1):
        a,b=map(self.expr,n.children)
        if type(a) is not int or type(b) is not int or type(step) is not int or step<=0:self.fail(n,'Range requires integer bounds and positive step')
        direction=1 if a<=b else -1
        r=range(a,b+(direction if n.value=='..' else 0),direction*step)
        if len(r)>100000:self.fail(n,'Range limit exceeded')
        return r
    def foreach(self,n):
        c=list(n.children); bindings=[]
        while c and c[0].kind=='TemporaryBinding':bindings.append(c.pop(0))
        source=c.pop(0); mods={x.kind:x for x in c if x.kind!='Block'}
        if any(x not in ('StepClause','WhereClause','SkipClause','TakeClause','IndexBinding','CompletedClause','EmptyClause') for x in mods):self.fail(n,'Unsupported iteration modifier')
        body=next(x for x in c if x.kind=='Block')
        if 'StepClause' in mods:
            if source.kind!='RangeExpression':self.fail(n,'Step requires range')
            values=self.make_range(source,self.expr(mods['StepClause'].children[0]))
        else:values=self.expr(source)
        if type(values) not in (list,tuple,dict,range,str):self.fail(n,'Not iterable')
        if len(bindings)!=1 and not (len(bindings)==2 and type(values) is dict):self.fail(n,'Unsupported iteration bindings')
        skip=self.expr(mods['SkipClause'].children[0]) if 'SkipClause' in mods else 0
        take=self.expr(mods['TakeClause'].children[0]) if 'TakeClause' in mods else 100000
        if any(type(x) is not int or x<0 for x in (skip,take)):self.fail(n,'Skip and take require nonnegative integers')
        index=mods.get('IndexBinding'); offset=self.expr(index.children[1]) if index and len(index.children)>1 else 0
        if type(offset) is not int:self.fail(n,'Index offset must be int')
        original=list(values) if type(values) in (list,dict) else None
        entered=0; broken=False
        for i,value in enumerate(values):
            self.tick(n)
            if entered>=take:break
            self.scopes.append({})
            try:
                for binding,val in zip(bindings,[value,values[value] if type(values) is dict else None]):
                    self.bind(binding.children[0],val,t=self.typename(binding.children[1]) if len(binding.children)>1 else 'any')
                if index:self.bind(index.children[0].children[0],i+offset)
                if 'WhereClause' in mods and not self.truth(mods['WhereClause'].children[0]):continue
                if skip:skip-=1;continue
                entered+=1
                try:self.stmt(body)
                except TuxContinue:pass
                except TuxBreak:broken=True
                if original is not None and list(values)!=original:self.fail(n,'Collection changed during iteration')
                if broken:break
            finally:self.scopes.pop()
        if not broken and 'CompletedClause' in mods:self.stmt(mods['CompletedClause'].children[0])
        if not entered and 'EmptyClause' in mods:self.stmt(mods['EmptyClause'].children[0])
    def validate_permissions(self,root):
        # Declarations are metadata, never executable expressions.
        self.declared_permissions = {}
        summary=[]; required=[]
        def capability(node):
            if node.kind=='Identifier': return node.value
            if node.kind=='MemberAccess': return capability(node.children[0])+'.'+node.children[1].value
            raise TuxFault('PermissionError','Invalid capability name')
        def literal(node):
            if node.kind!='Literal' or not node.value.startswith(('"','raw"')):
                raise TuxFault('PermissionError','Permission arguments must be literal strings')
            return self.string_value(node)
        stack=[(root,None)]
        while stack:
            node,parent=stack.pop()
            if node.kind=='PermissionDeclaration':
                if parent is not root: raise TuxFault('PermissionError','Permissions must be declared at top level')
                for entry in node.children:
                    target=entry.children[0]; args=()
                    if target.kind=='Call':
                        args=tuple(literal(x) for x in target.children[1:]); target=target.children[0]
                    name=capability(target)
                    status=TuxCapabilityRegistry.status(name)
                    if status=='unknown': raise TuxFault('PermissionError','Unknown capability: '+name)
                    reason=literal(entry.children[1]) if len(entry.children)>1 else ""
                    if args and status=='granted': raise TuxFault('PermissionError','Scoped grants are not supported: '+name)
                    if len(summary)>=100: raise TuxHardLimit('Permission declaration budget exceeded')
                    key=(name,args)
                    if key in self.declared_permissions: raise TuxFault('PermissionError','Duplicate permission: '+name)
                    self.declared_permissions[key]=entry.value
                    summary.append((entry.value,name,args,reason,status))
                    if entry.value=='require': required.append((name,args))
            else:
                stack.extend((child,node) for child in reversed(node.children))
        if summary and self.review is not None:
            decision=self.review((self.profile,tuple(summary)))
            if decision is False or decision is None: raise TuxHardLimit("Permission review cancelled")
            if type(decision) is dict:
                for key,text in decision.items():
                    if ('files.read',(key,)) in self.declared_permissions and type(key) is str and type(text) is str and len(text)<=100000:
                        self.host_snapshots[key]=text
                if len(self.host_snapshots)>10 or sum(map(len,self.host_snapshots.values()))>1000000:raise TuxHardLimit('Selected file budget exceeded')
        for name,args in required:
            if name=='files.read' and len(args)==1 and args[0] in self.host_snapshots:continue
            TuxCapabilityRegistry.require(name)
    def stmt(self,n):
        self.tick(n);k=n.kind;c=n.children
        if k in ('Program','Block'):
            if k=='Block':self.scopes.append({})
            self.defer_frames.append([])
            try:
                for x in c:
                    if x.kind=='FunctionDeclaration':
                        fn=TuxFunction(x,tuple(self.scopes))
                        self.bind(x.children[0],fn,True)
                        for group in (z for z in x.children if z.kind=='FunctionAliases'):
                            for alias in group.children:self.bind(alias,fn,True)
                for x in c:
                    if x.kind!='FunctionDeclaration':self.stmt(x)
            finally:
                import sys
                pending=self.defer_frames.pop(); primary=sys.exc_info()[1]
                try:
                    if not isinstance(primary,TuxHardLimit):
                        first=None
                        for action in reversed(pending):
                            try:self.guarded(lambda:self.stmt(action) if action.kind=='Block' else self.expr(action))
                            except TuxHardLimit:raise
                            except TuxFault as fault:
                                if first is None:first=fault
                        if first is not None and (primary is None or isinstance(primary,(TuxReturn,TuxBreak,TuxContinue))):raise first
                finally:
                    if k=='Block':self.scopes.pop()
        elif k in ('PermissionDeclaration','LimitDeclaration'):pass # validated before execution
        elif k=='ImportDeclaration':self.import_modules(n)
        elif k=='DeferStatement':
            if not self.defer_frames:self.fail(n,'No active defer scope')
            self.defer_frames[-1].append(c[0])
        elif k in ('VariableDeclaration','ConstantDeclaration'):
            rest=list(c[1:]);t='any'
            if rest and rest[0].kind in ('Type','NullableType','UnionType'):t=self.typename(rest.pop(0))
            if len(rest)>1 or (rest and ',' in self.source[c[0].end:rest[0].start]):self.fail(n,'Multiple declarations not supported')
            v=self.expr(rest[0]) if rest else {'int':0,'float':0.0,'bool':False,'string':''}.get(t)
            self.bind(c[0],v,k=='ConstantDeclaration',t)
        elif k=='ErrorDeclaration':
            if len(c)!=1:self.fail(n,'Custom error fields not yet supported')
            self.bind(c[0],TuxErrorType(c[0].value),True)
        elif k in ('ClassDeclaration','RecordDeclaration','EnumDeclaration'):self.declare_object(n)
        elif k=='AssignmentStatement' and len(c)==2 and c[0].kind in ('Identifier','MemberAccess'):
            if c[0].kind=='Identifier':b=self.lookup(c[0])
            else:
                obj=self.expr(c[0].children[0]);key=c[0].children[1].value
                if not isinstance(obj,TuxObject) or key not in obj.fields:self.fail(n,'Unknown assignable field')
                b=obj.fields[key]
            v=self.expr(c[1])
            if b[1]:self.fail(n,'Cannot reassign constant')
            if n.value!='=':v=self.binary(n,n.value[:-1],b[0],v)
            b[0]=self.convert(n,v,b[2])
        elif k=='TryStatement':self.try_statement(n)
        elif k=='ThrowStatement':
            if not c:
                if not self.active_faults:self.fail(n,'No active error to rethrow')
                raise self.active_faults[-1]
            fault=self.expr(c[0])
            if not isinstance(fault,TuxFault):self.fail(n,'throw requires an error object')
            if len(c)>1:
                cause=self.expr(c[1].children[0])
                if not isinstance(cause,TuxFault):self.fail(n,'Cause must be an error object')
                fault.cause=cause
            raise fault
        elif k=='ForEachStatement':self.foreach(n)
        elif k=='ExpressionStatement':self.expr(c[0])
        elif k in ('IfStatement','UnlessStatement'):
            if self.truth(c[0])==(k=='IfStatement'):self.stmt(c[1])
            elif len(c)>2:self.stmt(c[2])
        elif k in ('WhileStatement','UntilStatement') and len(c)==2:
            while self.truth(c[0])==(k=='WhileStatement'):
                try:self.stmt(c[1])
                except TuxBreak:break
                except TuxContinue:continue
        elif k=='ReturnStatement' and self.depth:raise TuxReturn(self.expr(c[0]) if c else None)
        elif k=='BreakStatement' and not c:raise TuxBreak()
        elif k=='ContinueStatement' and not c:raise TuxContinue()
        elif k=='AssertStatement':
            if not self.truth(c[0]):self.fail(n,'Assertion failed')
        else:self.fail(n,'Unsupported statement: '+k)
    def validate_limits(self,root):
        caps={'memory':('MiB',256),'execution':('seconds',60),'recursion':(None,40),'output':('bytes',100000)}
        values={}; stack=[(root,None)]
        while stack:
            node,parent=stack.pop()
            if node.kind!='LimitDeclaration':
                stack.extend((child,node) for child in node.children); continue
            if parent is not root: raise TuxHardLimit('Limits must be declared at top level')
            for entry in node.children:
                key,value=entry.children; name=key.value
                if name not in caps or name in values: raise TuxHardLimit('Unknown or duplicate resource limit: '+name)
                unit,maximum=caps[name]
                if name=='output' and value.kind=='Call' and len(value.children)==2 and value.children[0].value in ('KiB','MiB'):
                    unit=value.children[0].value
                if unit:
                    if value.kind!='Call' or len(value.children)!=2 or value.children[0].kind!='Identifier' or value.children[0].value!=unit: raise TuxHardLimit('Invalid resource limit unit: '+name)
                    value=value.children[1]
                if value.kind!='Literal' or not re.fullmatch(r'[0-9]{1,9}',value.value): raise TuxHardLimit('Resource limits require positive integer literals')
                amount=int(value.value)*({'KiB':1024,'MiB':1048576}.get(unit,1) if name=='output' else 1)
                if not 1<=amount<=maximum: raise TuxHardLimit('Resource limit outside host policy: '+name)
                values[name]=amount
        self.output_limit=values.get('output',100000); self.depth_limit=values.get('recursion',40)
        self.execution_limit=values.get('execution',60); self.memory_limit=values.get('memory',256)
        if self.worker_limits and sys.platform.startswith('linux'):
            tux_os_limits(self.memory_limit)
        elif 'memory' in values: raise TuxHardLimit('OS memory limits unavailable')

    def run(self):
        if self.stop.is_set():raise TuxHardLimit('Execution stopped')
        lex=TuxLexer().lex(self.source); parsed=TuxParser().parse(self.source,lex)
        sem=TuxSemanticAnalyzer();sem.source=self.source
        diagnostics=list(lex.diagnostics)+list(parsed.diagnostics)+list(sem.analyze(parsed))
        errors=[d for d in diagnostics if '-W-' not in d.code]
        if errors:raise TuxRuntimeError(errors[0].code+': '+errors[0].message)
        self.validate_limits(parsed.root)
        self.validate_permissions(parsed.root)
        self.deadline=time.monotonic()+self.execution_limit
        self.tick(parsed.root)
        try:self.stmt(parsed.root)
        except (TuxBreak,TuxContinue):raise TuxRuntimeError('Loop control outside loop')
        except (ArithmeticError,TypeError,ValueError,RecursionError,LookupError) as e:raise TuxRuntimeError(str(e)) from None


def tux_wire_write(stream, value):
    frame=json.dumps(value, ensure_ascii=True, allow_nan=False)+"\n"
    if len(frame)>8000000: raise ValueError("IPC frame too large")
    stream.write(frame)
    stream.flush()


def tux_wire_read(stream):
    line=stream.readline(8000001)
    if not line: raise EOFError('Runtime channel closed')
    if len(line)>8000000 or not line.endswith('\n'): raise ValueError('Invalid runtime frame')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: raise ValueError('Duplicate IPC key')
            result[key]=value
        return result
    def invalid(value): raise ValueError('Non-finite IPC value')
    try: return json.loads(line,object_pairs_hook=pairs,parse_constant=invalid)
    except RecursionError: raise ValueError('IPC nesting exceeded') from None


def tux_os_limits(memory=256):
    import resource
    for kind,requested in ((resource.RLIMIT_AS,memory*1048576),(resource.RLIMIT_CPU,65)):
        soft,hard=resource.getrlimit(kind)
        limit=min([requested]+[v for v in (soft,hard) if v!=resource.RLIM_INFINITY])
        resource.setrlimit(kind,(limit,limit))


def tux_worker_main():
    def send(kind,value): tux_wire_write(sys.stdout,[kind,value])
    def read(prompt):
        send('input',prompt)
        return tux_wire_read(sys.stdin)
    try:
        if sys.platform.startswith("linux"): tux_os_limits()
        request=tux_wire_read(sys.stdin)
        if type(request) is not list or len(request)!=2: raise ValueError('Invalid startup request')
        source,profile=request
        if profile not in ('Restricted','Project','Trusted','Testing'): raise ValueError('Invalid profile')
        if type(source) is not str or len(source)>1000000: raise TuxHardLimit('Source size limit exceeded')
        runtime=TuxInterpreter(source,lambda text:send('output',text),None,read,profile,lambda payload:read(('permissionReview',payload)))
        runtime.worker_limits=True
        runtime.run()
        send('output','\n[Execution finished]\n')
    except MemoryError: send('output','\n[TUX stopped] Memory limit exceeded\n')
    except TuxHardLimit as exc: send('output','\n[TUX stopped] '+str(exc)+'\n')
    except TuxRuntimeError as exc: send('output','\n[TUX runtime] '+str(exc)+'\n')
    except Exception as exc: send('output','\n[TUX internal error] '+type(exc).__name__+': '+str(exc)+'\n')
    return 0


def tux_worker_command():
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--tux-worker']
    return [sys.executable, '-u', os.path.abspath(__file__), '--tux-worker']


def tux_process_run(source,profile,stop,output,responses):
    proc=None
    incoming=queue.Queue(maxsize=128)
    def reader():
        try:
            while not stop.is_set():
                item=tux_wire_read(proc.stdout)
                while not stop.is_set():
                    try: incoming.put(item,timeout=.05); break
                    except queue.Full: pass
        except EOFError: pass
        except (ValueError,OSError) as exc:
            while not stop.is_set():
                try: incoming.put(["protocolError",str(exc)],timeout=.05); break
                except queue.Full: pass
        finally:
            while not stop.is_set():
                try: incoming.put(None,timeout=.05); break
                except queue.Full: pass
    try:
        if len(source)>1000000: raise ValueError('Source size limit exceeded')
        proc=subprocess.Popen(tux_worker_command(),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        threading.Thread(target=reader,daemon=True).start()
        tux_wire_write(proc.stdin,[source,profile])
        deadline=time.monotonic()+65
        forwarded=0
        while not stop.is_set():
            if time.monotonic()>=deadline:
                output("\n[TUX stopped] Host execution time limit exceeded\n"); break
            try: item=incoming.get(timeout=.05)
            except queue.Empty: continue
            if item is None:
                if proc.wait(timeout=1)!=0: output('\n[TUX runtime process exited unexpectedly]\n')
                break
            if not isinstance(item,list) or len(item)!=2: raise ValueError('Invalid runtime message')
            kind,value=item
            if kind=='output' and type(value) is str:
                forwarded+=len(value.encode('utf-8',errors='replace'))
                if forwarded>110000: raise ValueError('Runtime output transport budget exceeded')
                output(value)
            elif kind=='input' and isinstance(value,(str,list)):
                if isinstance(value,list):
                    if len(value)!=2: raise ValueError('Invalid input request')
                    mode,prompt=value
                    if mode=='permissionReview':
                        if type(prompt) is not list or len(prompt)!=2 or prompt[0]!=profile or type(prompt[1]) is not list or len(prompt[1])>100: raise ValueError('Invalid permission review')
                        for entry in prompt[1]:
                            if type(entry) is not list or len(entry)!=5: raise ValueError('Invalid permission entry')
                            m,n,a,r,st=entry
                            if m not in ('require','optional') or type(n) is not str or type(a) is not list or any(type(x) is not str for x in a) or type(r) is not str or st not in ('granted','restricted'): raise ValueError('Invalid permission entry')
                    elif mode not in ('confirm','inputPassword') or type(prompt) is not str or len(prompt)>100000: raise ValueError('Invalid input request')
                    value=tuple(value)
                elif len(value)>100000: raise ValueError('Input prompt too large')
                output(('input',value))
                paused=time.monotonic()
                while not stop.is_set():
                    try: response=responses.get(timeout=.05); break
                    except queue.Empty:
                        if proc.poll() is not None: raise EOFError('Runtime exited during input')
                deadline+=time.monotonic()-paused
                if not stop.is_set(): tux_wire_write(proc.stdin,response)
            elif kind=='protocolError': raise ValueError('Invalid runtime frame: '+value)
            else: raise ValueError('Invalid runtime message')
        if stop.is_set(): output('\n[TUX stopped] Execution stopped\n')
    except (OSError,ValueError,EOFError,UnicodeError,subprocess.SubprocessError) as exc:
        output('\n[TUX process error] '+str(exc)+'\n')
    finally:
        stop.set()
        if proc is not None:
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=.5)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait()
            proc.stdin.close(); proc.stdout.close()


if __name__=='__main__' and sys.argv[1:]==['--version']:
    print('Tux Studio 0.10.2.1 (development preview)')
    sys.exit(0)

if __name__=='__main__' and sys.argv[1:]==['--tux-worker']:
    sys.exit(tux_worker_main())


try:
    from PySide6.QtCore import Qt, QRect, QSize, QEvent, QTimer, QSaveFile, QIODevice, QSettings, QStandardPaths, QLockFile
    from PySide6.QtGui import (QAction, QColor, QFont, QFontDatabase, QIcon,
                               QPainter, QPen, QPixmap, QTextFormat, QTextCursor, QPalette, QShortcut, QKeySequence, QSyntaxHighlighter, QTextCharFormat)
    from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
        QHBoxLayout, QLabel, QToolButton, QMenuBar, QSplitter, QTabWidget,
        QPlainTextEdit, QTextEdit, QMessageBox, QStatusBar, QStyle, QSizeGrip, QButtonGroup, QFileDialog, QInputDialog, QDialog, QCheckBox, QDialogButtonBox, QScrollArea, QLineEdit, QPushButton, QSpinBox, QFormLayout, QComboBox, QTableWidget, QTableWidgetItem, QToolTip, QTreeWidget, QTreeWidgetItem, QKeySequenceEdit)
except ImportError:
    raise SystemExit('PySide6 is required. Install it with: python -m pip install PySide6')

VERSION = '0.10.2.1'


def penguin():
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    for color, rect in [('#e8ad42',(8,51,23,10)),('#e8ad42',(33,51,23,10)),
                        ('#252830',(10,5,44,52)),('#f5f5f5',(18,24,28,31)),
                        ('#ffffff',(19,14,12,15)),('#ffffff',(33,14,12,15)),
                        ('#252830',(25,19,5,6)),('#252830',(34,19,5,6)),
                        ('#e8ad42',(25,27,14,8))]:
        p.setBrush(QColor(color)); p.drawEllipse(QRect(*rect))
    p.end()
    return QIcon(pix)


def theme_icon(mode, color):
    """Draw platform-independent sun and crescent icons at high resolution."""
    pix = QPixmap(48, 48)
    pix.setDevicePixelRatio(2)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    if mode == 'Light':
        p.drawEllipse(QRect(8, 8, 8, 8))
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(round(12 + 7*math.cos(a)), round(12 + 7*math.sin(a)),
                       round(12 + 10*math.cos(a)), round(12 + 10*math.sin(a)))
    else:
        from PySide6.QtGui import QPainterPath
        path = QPainterPath()
        path.moveTo(12, 3)
        path.cubicTo(1, 4, 0, 19, 12, 21)
        path.cubicTo(17, 22, 21, 18, 22, 14)
        path.cubicTo(12, 18, 6, 10, 12, 3)
        p.drawPath(path)
    p.end()
    return QIcon(pix)


class Gutter(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def paintEvent(self, event):
        e = self.editor
        p = QPainter(self)
        p.fillRect(event.rect(), QColor(e.colors['panel']))
        p.setFont(e.font())
        block = e.firstVisibleBlock()
        while block.isValid():
            top = round(e.blockBoundingGeometry(block).translated(e.contentOffset()).top())
            height = round(e.blockBoundingRect(block).height())
            if top > event.rect().bottom():
                break
            if block.isVisible() and top + height >= event.rect().top():
                p.setPen(QColor(e.colors['fg'] if block == e.textCursor().block() else e.colors['muted']))
                p.drawText(0, top, self.width()-20, e.fontMetrics().height(),
                           Qt.AlignmentFlag.AlignRight, str(block.blockNumber()+1))
                if block.blockNumber() in e.folds:
                    p.drawText(self.width()-17, top, 16, e.fontMetrics().height(), Qt.AlignmentFlag.AlignCenter, '▸' if block.blockNumber() in e.collapsed else '▾')
            block = block.next()
        p.end()

    def mousePressEvent(self,event):
        if event.position().x() < self.width()-20: return
        e=self.editor
        block=e.cursorForPosition(event.position().toPoint()).block()
        e.toggle_fold(block.blockNumber())


LANG_DEFAULTS=dict(highlighting=True,live=True,interpolation=True,escapes=True,documentation=True,unicode=True,counters=True,tooltips=True,suggestions=True,delay=350,detail='Standard')

class TuxSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self,e,options):
        # Construct detached: Qt may invoke highlightBlock during attachment.
        super().__init__(e)
        self.e=e; self.options=options; self.spans={}; self.error_spans={}; self.failed=False
        self.setDocument(e.document())
    def highlightBlock(self,text):
        if self.failed: return
        try:
            opts=self.options
            dark=self.e.colors.get('dark',False)
            colors=('#c792ea','#82aaff','#c3e88d','#f78c6c','#8997a7','#ffcb6b','#89ddff') if dark else ('#8629a0','#1754a5','#38761d','#b44b19','#68757f','#956100','#007c91')
            groups=[('KEYWORD','CONTEXTUAL','BOOLEAN','NULL'),('TYPE_IDENTIFIER',),('STRING','RAW_STRING','BINARY_STRING','CHARACTER'),('NUMBER',),('COMMENT','DOCUMENTATION'),('BUILTIN',),('OPERATOR','INTERPOLATION_START','INTERPOLATION_END','ESCAPE')]
            for start,length,kind in self.spans.get(self.currentBlock().blockNumber(),[]):
                color=next((colors[i] for i,g in enumerate(groups) if kind in g),None)
                if kind=='ESCAPE' and not opts['escapes']: color=colors[2]
                if color and opts['highlighting']:
                    fmt=QTextCharFormat(); fmt.setForeground(QColor(color))
                    if kind=='DOCUMENTATION' and opts['documentation']: fmt.setFontItalic(True)
                    self.setFormat(start,length,fmt)
            if opts['live']:
                for start,length,warning in self.error_spans.get(self.currentBlock().blockNumber(),[]):
                    if warning and not opts['unicode']: continue
                    for pos in range(start,start+length):
                        fmt=self.format(pos); fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
                        color=QColor(('#e5b567' if warning else '#ff6b68') if dark else ('#986400' if warning else '#c62828')); fmt.setUnderlineColor(color); fmt.setForeground(color); self.setFormat(pos,1,fmt)
        except Exception as exc:
            self.failed=True
            print(f'TUX highlighting disabled for this document: {type(exc).__name__}: {exc}',file=sys.stderr)


def tux_analyze_snapshot(source, enabled):
    lexed=TuxLexer().lex(source) if enabled else TuxLexResult([],[])
    parsed=TuxParser().parse(source,lexed) if enabled else None
    diagnostics=list(lexed.diagnostics)+list(parsed.diagnostics if parsed else ())
    semantic=TuxSemanticAnalyzer(); semantic.source=source
    diagnostics.extend(semantic.analyze(parsed if not any('-E-' in d.code for d in diagnostics) else None))
    return lexed,parsed,diagnostics,semantic


class TuxEditorLanguage:
    def __init__(self,e,studio):
        self.e=e; self.studio=studio; self.mode='Automatic'; self.result=TuxLexResult([],[]); self.source=''; self.positions=[0]; self.busy=False; self.last_error=None; self.pending=False
        self.highlighter=TuxSyntaxHighlighter(e,studio.language_options); self.timer=QTimer(e); self.timer.setSingleShot(True); self.timer.timeout.connect(self.analyze); e.textChanged.connect(self.schedule)
        self.observed_source=e.toPlainText(); self.revision=0; self.applied_revision=-1; self.queued=None; self.mailbox=queue.Queue(); self.poll=QTimer(e); self.poll.timeout.connect(self.collect_worker)
    def enabled(self): return self.mode=='TUX' or (self.mode=='Automatic' and (self.e.path is None or self.e.path.suffix.lower()=='.tux'))
    def schedule(self):
        # Qt can emit textChanged for formatting-only changes.
        source=self.e.toPlainText()
        if source==self.observed_source: return
        self.observed_source=source
        self.revision+=1; self.queued=None; self.pending=True; self.last_error=None
        self.highlighter.spans={}; self.highlighter.error_spans={}
        self.timer.start(self.studio.language_options['delay'])
    def analyze(self, synchronous=False):
        self.timer.stop(); self.pending=False
        self.revision+=1
        self.observed_source=self.e.toPlainText()
        request=(self.revision,self.observed_source,self.enabled())
        if synchronous:
            self.queued=None
            try: self.apply_snapshot(request,tux_analyze_snapshot(*request[1:]))
            except Exception as exc: self.analysis_error(exc)
            return
        self.queued=request
        self.highlighter.spans={}; self.highlighter.error_spans={}
        self.highlighter.rehighlight(); self.e.highlight(); self.studio.update_status()
        self.start_worker()
    def start_worker(self):
        if self.busy or self.queued is None: return
        request=self.queued; self.queued=None; self.busy=True
        mailbox=self.mailbox
        def work():
            try: mailbox.put((request,tux_analyze_snapshot(*request[1:]),None))
            except Exception as exc: mailbox.put((request,None,str(exc)))
        try:
            threading.Thread(target=work,daemon=True).start()
        except RuntimeError:
            self.busy=False
            self.analyze(synchronous=True)
            return
        self.poll.start(30)
    def collect_worker(self):
        try: request,result,error=self.mailbox.get_nowait()
        except queue.Empty: return
        self.busy=False; self.poll.stop()
        if request==(self.revision,self.e.toPlainText(),self.enabled()):
            if error is not None: self.analysis_error(error)
            else:
                try: self.apply_snapshot(request,result)
                except Exception as exc: self.analysis_error(exc)
        self.start_worker()
    def analysis_error(self,exc):
        self.last_error=str(exc); self.source=None
        self.highlighter.spans={}; self.highlighter.error_spans={}
        self.highlighter.rehighlight(); self.e.highlight(); self.studio.update_status()
        print('TUX language analysis failed: '+str(exc),file=sys.stderr)
    def apply_snapshot(self,request,result):
        self.source=request[1]; self.applied_revision=request[0]; self.positions=[0]
        for c in self.source: self.positions.append(self.positions[-1]+(2 if ord(c)>65535 else 1))
        self.result,self.parse_result,self.all_diagnostics,self.semantic_analyzer=result
        spans={}; lines=[0]+[m.end() for m in re.finditer('\n',self.source)]; nesting=0
        for t in self.result.tokens:
            if t.kind=='INTERPOLATION_START': nesting+=1
            kind='STRING' if nesting and not self.studio.language_options['interpolation'] else t.kind
            if t.kind=='INTERPOLATION_END': nesting=max(0,nesting-1)
            if kind in ('WHITESPACE','NEWLINE','EOF'): continue
            for line in range(t.line-1,bisect_right(lines,max(t.start,t.end-1))):
                a=max(t.start,lines[line]); b=min(t.end,lines[line+1]-1 if line+1<len(lines) else len(self.source)); base=self.positions[lines[line]]
                if b>a: spans.setdefault(line,[]).append((self.positions[a]-base,self.positions[b]-self.positions[a],kind))
        error_spans={}
        for d in self.all_diagnostics:
            for line in range(bisect_right(lines,d.start)-1,bisect_right(lines,max(d.start,d.end-1))):
                a=max(d.start,lines[line]); b=min(d.end,lines[line+1]-1 if line+1<len(lines) else len(self.source)); base=self.positions[lines[line]]
                if b>a: error_spans.setdefault(line,[]).append((self.positions[a]-base,self.positions[b]-self.positions[a],'-W-' in d.code))
        self.highlighter.error_spans=error_spans
        self.highlighter.spans=spans; self.last_error=None
        self.highlighter.rehighlight()
        self.e.highlight()
        self.studio.update_status()
    def diagnostics(self, manual=False):
        opts=self.studio.language_options
        if not self.enabled() or (self.applied_revision!=self.revision or self.source!=self.e.toPlainText()): return []
        if not manual and not opts['live']: return []
        return [d for d in getattr(self,"all_diagnostics",[]) if opts['unicode'] or '-W-' not in d.code]
    def status_text(self):
        if not self.enabled(): return ''
        if self.last_error: return 'Diagnostic analysis failed — see terminal'
        if not self.studio.language_options['live']: return 'Live diagnostics off'
        if (self.applied_revision!=self.revision or self.source!=self.e.toPlainText()): return 'Analyzing…'
        ds=self.diagnostics()
        return f"{sum('-E-' in d.code for d in ds)} errors · {sum('-W-' in d.code for d in ds)} warnings"
    def navigate(self,a,b):
        if (self.applied_revision!=self.revision or self.source!=self.e.toPlainText()): return
        c=self.e.textCursor(); c.setPosition(self.positions[a]); c.setPosition(self.positions[b],QTextCursor.MoveMode.KeepAnchor); self.e.setTextCursor(c); self.e.centerCursor()
    def selections(self):
        out=[]
        for d in self.diagnostics():
            c=QTextCursor(self.e.document()); c.setPosition(self.positions[d.start]); c.setPosition(self.positions[d.end],QTextCursor.MoveMode.KeepAnchor)
            sel=QTextEdit.ExtraSelection(); sel.cursor=c; sel.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline); sel.format.setUnderlineColor(QColor('#e5a33c' if '-W-' in d.code else '#ef5555')); out.append(sel)
        return out


class Editor(QPlainTextEdit):
    def __init__(self, colors):
        super().__init__()
        self.colors = colors
        self.options = dict(completion=True, guides=True, current=True, wrap=True, whitespace=False, margin=120)
        self.folds = {}; self.collapsed = set(); self.search_ranges = []
        self.setObjectName('editor')
        family = 'JetBrains Mono' if 'JetBrains Mono' in QFontDatabase.families() else QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
        self.editor_family = family
        self.zoom_size = 13
        self.zoom_callback = None
        self.setFont(QFont(family, 13))
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ')*4)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.gutter = Gutter(self)
        self.blockCountChanged.connect(self.update_gutter)
        self.updateRequest.connect(self.scroll_gutter)
        self.cursorPositionChanged.connect(self.highlight)
        self.update_gutter()
        self.highlight()
        self.textChanged.connect(self.structure_changed)

    def update_gutter(self, *_):
        width = 32 + self.fontMetrics().horizontalAdvance('9') * max(2, len(str(self.blockCount())))
        self.setViewportMargins(width, 0, 0, 0)
        r = self.contentsRect()
        self.gutter.setGeometry(r.left(), r.top(), width, r.height())
        self.gutter.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_gutter()

    def scroll_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())

    def apply_options(self, options):
        self.options = dict(options)
        self.setLineWrapMode(self.LineWrapMode.WidgetWidth if options['wrap'] else self.LineWrapMode.NoWrap)
        from PySide6.QtGui import QTextOption
        opt=self.document().defaultTextOption()
        opt.setFlags(QTextOption.Flag.ShowTabsAndSpaces if options['whitespace'] else QTextOption.Flag(0))
        self.document().setDefaultTextOption(opt)
        self.highlight(); self.viewport().update()

    def structure_changed(self):
        self.collapsed.clear()
        self.search_ranges=[]
        self.folds.clear()
        stack=[]; block=self.document().firstBlock()
        while block.isValid():
            block.setVisible(True); block.setLineCount(max(1,block.layout().lineCount()))
            line=block.text(); n=block.blockNumber()
            if line.strip():
                indent=len(line)-len(line.lstrip())
                while stack and indent<=stack[-1][0]:
                    _,start=stack.pop()
                    if n>start+1: self.folds[start]=n-1
                stack.append((indent,n))
            block=block.next()
        while stack:
            _,start=stack.pop()
            if self.blockCount()-1>start: self.folds[start]=self.blockCount()-1
        self.document().markContentsDirty(0,self.document().characterCount())
        self.highlight()

    def toggle_fold(self,n):
        if n not in self.folds: return
        if n in self.collapsed: self.collapsed.remove(n)
        else: self.collapsed.add(n)
        block=self.document().firstBlock()
        while block.isValid():
            i=block.blockNumber(); visible=not any(k<i<=self.folds[k] for k in self.collapsed)
            block.setVisible(visible); block.setLineCount(max(1,block.layout().lineCount()) if visible else 0); block=block.next()
        self.document().markContentsDirty(0,self.document().characterCount()); self.viewport().update(); self.gutter.update()

    def highlight(self):
        selections=[]
        def add(cursor,color,full=False):
            sel=QTextEdit.ExtraSelection(); sel.cursor=cursor; sel.format.setBackground(QColor(color))
            if full: sel.format.setProperty(QTextFormat.Property.FullWidthSelection,True)
            selections.append(sel)
        c=self.textCursor(); c.clearSelection()
        if self.options['current']: add(c,self.colors['line'],True)
        for start,end in self.search_ranges:
            cur=QTextCursor(self.document()); cur.setPosition(start); cur.setPosition(end,QTextCursor.MoveMode.KeepAnchor); add(cur,'#96752c')
        pos=c.position(); doc=self.document(); pairs={'(':')','[':']','{':'}'}; reverse={v:k for k,v in pairs.items()}
        for at in (pos-1,pos):
            if not 0<=at<doc.characterCount()-1: continue
            ch=doc.characterAt(at)
            if ch not in pairs and ch not in reverse: continue
            forward=ch in pairs; target=(pairs if forward else reverse)[ch]; depth=0; match=None
            for j in range(at+(1 if forward else -1),doc.characterCount()-1 if forward else -1,1 if forward else -1):
                v=doc.characterAt(j)
                if v==ch: depth+=1
                elif v==target:
                    if depth==0: match=j; break
                    depth-=1
            for j in ([at,match] if match is not None else [at]):
                cur=QTextCursor(doc); cur.setPosition(j); cur.movePosition(QTextCursor.MoveOperation.Right,QTextCursor.MoveMode.KeepAnchor); add(cur,self.colors['accent'] if match is not None else '#c74747')
            break
        selections.extend(self.language.selections() if hasattr(self,"language") else []); self.setExtraSelections(selections); self.gutter.update(); self.viewport().update()

    def paintEvent(self,event):
        super().paintEvent(event)
        p=QPainter(self.viewport()); p.setPen(QColor(self.colors['border']))
        step=self.fontMetrics().horizontalAdvance(' '); origin=self.contentOffset().x()+self.document().documentMargin()
        if self.options['margin']:
            x=round(origin+step*self.options['margin']); p.drawLine(x,0,x,self.viewport().height())
        if self.options['guides']:
            block=self.firstVisibleBlock()
            while block.isValid():
                y=round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top()); h=round(self.blockBoundingRect(block).height())
                if y>self.viewport().height(): break
                if block.isVisible():
                    line=block.text(); indent=len(line)-len(line.lstrip(' '))
                    for n in range(0,indent,4):
                        x=round(origin+n*step); p.drawLine(x,y,x,y+h)
                block=block.next()
        p.end()

    def set_zoom_size(self, size):
        self.zoom_size = max(8, min(40, int(size)))
        # Explicit widget stylesheet overrides the inherited QWidget 13px rule.
        self.setStyleSheet(f'QPlainTextEdit#editor {{ font-size: {self.zoom_size}pt; }}')
        font = QFont(self.editor_family, self.zoom_size)
        self.setFont(font)
        self.document().setDefaultFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ')*4)
        self.update_gutter()
        self.viewport().update()
        self.gutter.update()

    def zoomIn(self,n=1):
        size = self.zoom_size + n
        if self.zoom_callback is not None: self.zoom_callback(size)
        else: self.set_zoom_size(size)

    def zoomOut(self,n=1): self.zoomIn(-n)
    def reset_zoom(self): self.zoomIn(13-self.zoom_size)
    def wheelEvent(self,event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y() or event.pixelDelta().y()
            if delta: self.zoomIn(1 if delta > 0 else -1)
            event.accept()
        else: super().wheelEvent(event)

    def line_action(self,action):
        c=self.textCursor(); start=c.block().position(); line=c.block().text(); c.beginEditBlock()
        c.setPosition(start)
        if action=='duplicate': c.insertText(line+'\n')
        elif action=='delete':
            c.movePosition(QTextCursor.MoveOperation.EndOfBlock,QTextCursor.MoveMode.KeepAnchor)
            if not c.atEnd(): c.movePosition(QTextCursor.MoveOperation.Right,QTextCursor.MoveMode.KeepAnchor)
            c.removeSelectedText()
        else:
            other=c.block().previous() if action=='up' else c.block().next()
            if other.isValid():
                first=other if action=='up' else c.block(); second=c.block() if action=='up' else other
                c.setPosition(first.position()); c.setPosition(second.position()+second.length()-1,QTextCursor.MoveMode.KeepAnchor)
                c.insertText(second.text()+'\n'+first.text()); c.setPosition(first.position() if action=='up' else first.position()+len(second.text())+1)
        c.endEditBlock(); self.setTextCursor(c)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
        else: super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
        else: super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
            event.acceptProposedAction()
            self.files_dropped(paths)
        else: super().dropEvent(event)

    def keyPressEvent(self,event):
        key=event.key(); mod=event.modifiers(); c=self.textCursor(); text=event.text(); pairs={'(':')','[':']','{':'}','"':'"',"'":"'"}
        if key in (Qt.Key.Key_Tab,Qt.Key.Key_Backtab):
            if key==Qt.Key.Key_Tab and not c.hasSelection(): self.insertPlainText(' '*(4-(c.positionInBlock()%4))); return
            start=c.selectionStart(); end=c.selectionEnd(); block=self.document().findBlock(start); positions=[]
            while block.isValid() and block.position()<=end:
                if block.position()==end and end>start: break
                positions.append(block.position()); block=block.next()
            c.beginEditBlock()
            for pos in reversed(positions):
                c.setPosition(pos)
                if key==Qt.Key.Key_Tab: c.insertText('    ')
                else:
                    count=min(4,len(c.block().text())-len(c.block().text().lstrip(' ')))
                    c.setPosition(pos+count,QTextCursor.MoveMode.KeepAnchor); c.removeSelectedText()
            c.endEditBlock(); return
        if key in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and mod==Qt.KeyboardModifier.NoModifier:
            prefix=c.block().text()[:c.positionInBlock()]; indent=re.match(r'[ \t]*',prefix).group(); extra='    ' if prefix.rstrip().endswith(('{','[','(',':')) else ''
            c.insertText('\n'+indent+extra); self.setTextCursor(c); return
        if self.options['completion'] and not (mod & (Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.AltModifier|Qt.KeyboardModifier.MetaModifier)):
            if text in pairs.values() and not c.hasSelection() and self.document().characterAt(c.position())==text:
                c.movePosition(QTextCursor.MoveOperation.Right); self.setTextCursor(c); return
            if text in pairs:
                selected=c.selectedText().replace('\u2029','\n'); c.insertText(text+selected+pairs[text]); c.movePosition(QTextCursor.MoveOperation.Left); self.setTextCursor(c); return
        super().keyPressEvent(event)


class TitleBar(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setObjectName('titlebar')
        self.setFixedHeight(43)
        layout = QHBoxLayout(self); layout.setContentsMargins(12, 0, 5, 0); layout.setSpacing(9)
        logo = QLabel(); logo.setPixmap(window.windowIcon().pixmap(29,29)); layout.addWidget(logo)
        self.title = QLabel('Tux Studio'); self.title.setObjectName('brand'); layout.addWidget(self.title)
        self.filename = QLabel(); self.filename.setObjectName('muted'); layout.addWidget(self.filename)
        layout.addStretch()
        for text, tip, callback in [('−','Minimize',window.showMinimized),('□','Maximize / restore',window.toggle_maximize),('×','Close',window.close)]:
            b = QToolButton(); b.setText(text); b.setToolTip(tip); b.setFixedSize(42,32); b.clicked.connect(callback); layout.addWidget(b)
            if tip == 'Close': b.setObjectName('closeWindow')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window.windowHandle()
            if handle: handle.startSystemMove()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.window.toggle_maximize()


class TerminalSession(QPlainTextEdit):
    """PTY transport with a pyte VT screen and bounded scrollback."""
    def __init__(self, studio, cwd):
        super().__init__(); self.studio=studio; self.cwd=cwd; self.fd=None; self.pid=None; self.win=None; self.dead=False
        self.setReadOnly(True); self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setUndoRedoEnabled(False); self.setObjectName('nativeTerminal')
        self.screen=None; self.stream=None; self.queue=queue.Queue(maxsize=256); self.stop=threading.Event()
        self.timer=QTimer(self); self.timer.timeout.connect(self.poll)
        self.cursor_on=True; self.vt_caret=None
        self.blink_timer=QTimer(self); self.blink_timer.timeout.connect(self.blink_cursor); self.blink_timer.start(500)
        self.restyle()
        try:
            import pyte
            self.screen=pyte.HistoryScreen(80,24,history=10000); self.stream=pyte.ByteStream(self.screen)
            if os.name=='nt':
                from winpty import PtyProcess
                shell=shutil.which('pwsh') or shutil.which('powershell.exe')
                if not shell: raise RuntimeError('PowerShell not found')
                self.win=PtyProcess.spawn([shell,'-NoLogo'],cwd=str(cwd),dimensions=(24,80))
            else:
                import pty
                shell=os.environ.get('SHELL') or '/bin/bash'
                if not os.path.isfile(shell): shell='/bin/sh'
                # Start a fresh interpreter in a PTY; avoid executing Python in a forked Qt child.
                self.pid,self.fd=pty.fork()
                if self.pid==0:
                    try:
                        os.chdir(cwd); os.environ['TERM']='xterm-256color'; os.execv(shell,[shell,'-i'])
                    except BaseException: os._exit(127)
                os.set_blocking(self.fd,False)
            threading.Thread(target=self.reader,daemon=True).start(); self.timer.start(35); self.resize_pty()
        except Exception as exc:
            self.shutdown(); self.setPlainText('Terminal could not start: '+str(exc)+'\nInstall pyte (and pywinpty on Windows), then restart the session.')

    def reader(self):
        try:
            while not self.stop.is_set():
                if self.win is not None:
                    data=self.win.read(4096); data=data.encode('utf-8') if isinstance(data,str) else data
                else:
                    import select
                    fd=self.fd
                    if fd is None: break
                    if not select.select([fd],[],[],0.15)[0]: continue
                    try: data=os.read(fd,65536)
                    except BlockingIOError: continue
                if not data: break
                while not self.stop.is_set():
                    try: self.queue.put(data,timeout=.1); break
                    except queue.Full: pass
        except (OSError,EOFError,ValueError): pass
        except Exception: pass
        finally:
            if not self.stop.is_set():
                while not self.stop.is_set():
                    try: self.queue.put(None,timeout=.1); break
                    except queue.Full: pass

    def poll(self):
        changed=False
        for _ in range(64):
            try: data=self.queue.get_nowait()
            except queue.Empty: break
            if data is None:
                self.dead=True; self.timer.stop(); changed=True; break
            self.stream.feed(data); changed=True
        if changed: self.render()

    def blink_cursor(self):
        self.cursor_on = not self.cursor_on if self.studio.terminal_cursor_blink else True
        if self.isVisible(): self.viewport().update()

    def paintEvent(self,event):
        super().paintEvent(event)
        if not getattr(self,"screen",None) or self.dead or self.vt_caret is None or getattr(self.screen.cursor,"hidden",False): return
        if self.studio.terminal_cursor_blink and not self.cursor_on and self.hasFocus(): return
        rect=self.cursorRect(self.vt_caret)
        if not self.viewport().rect().intersects(rect): return
        painter=QPainter(self.viewport()); color=self.color('default')
        width=max(1,self.fontMetrics().horizontalAdvance('M')); height=rect.height()
        shape=self.studio.terminal_cursor_shape
        if shape=='Block':
            color.setAlpha(150); painter.fillRect(rect.x(),rect.y(),width,height,color)
        elif shape=='Underline': painter.fillRect(rect.x(),rect.bottom()-1,width,2,color)
        else: painter.fillRect(rect.x(),rect.y(),2,height,color)
        painter.end()

    def restyle(self):
        c=self.studio.colors; size=self.studio.terminal_size
        family=QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
        e=self.studio.tabs.currentWidget()
        if e: family=e.editor_family
        style=f'QPlainTextEdit#nativeTerminal {{font-size:{size}pt;background:{c.get("console","#191a1e")};}}'
        if self.styleSheet()!=style: self.setStyleSheet(style)
        self.setFont(QFont(family,size)); self.document().setDefaultFont(self.font())
        if self.screen: self.resize_pty(); self.render()
        self.viewport().update()

    def showEvent(self,event):
        super().showEvent(event)
        QTimer.singleShot(0,self.resize_pty)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if getattr(self,'screen',None): self.resize_pty()

    def resize_pty(self):
        if not self.screen or not self.isVisible(): return
        cols=max(2,self.viewport().width()//max(1,self.fontMetrics().horizontalAdvance('M')))
        rows=max(2,self.viewport().height()//max(1,self.fontMetrics().height()))
        if (cols,rows)==getattr(self,"pty_size",None): return
        if (cols,rows)!=(self.screen.columns,self.screen.lines): self.screen.resize(lines=rows,columns=cols)
        self.pty_size=(cols,rows)
        try:
            if self.win: self.win.setwinsize(rows,cols)
            elif self.fd is not None:
                import fcntl,termios,struct
                fcntl.ioctl(self.fd,termios.TIOCSWINSZ,struct.pack('HHHH',rows,cols,0,0))
        except Exception: pass

    def color(self,name,background=False):
        c=self.studio.colors
        if name=='default': return QColor(c['console'] if background else self.studio.terminal_color or c['fg'])
        palette={'black':'#202124','red':'#d74747','green':'#48a868','brown':'#b58b32','yellow':'#d6ad45','blue':'#528ce0','magenta':'#b66bd0','cyan':'#36aeb5','white':'#d4d4d4','brightblack':'#777777','brightred':'#ff6868','brightgreen':'#71d78a','brightyellow':'#f4d35e','brightblue':'#81b1ff','brightmagenta':'#e29af5','brightcyan':'#79e1e5','brightwhite':'#ffffff'}
        q=QColor(palette.get(name,'#'+name if re.fullmatch('[0-9a-fA-F]{6}',name) else name))
        return q if q.isValid() else QColor(c['fg'])

    def render(self):
        if not self.screen: return
        from PySide6.QtGui import QTextCharFormat
        bar=self.verticalScrollBar(); old=bar.value(); bottom=old>=bar.maximum()-1
        # Rebuild visible VT grid and scrollback, grouping adjacent cells by style.
        history=list(self.screen.history.top); lines=history+[self.screen.buffer[y] for y in range(self.screen.lines)]
        self.viewport().setUpdatesEnabled(False)
        try:
            self.vt_caret=None
            self.clear(); cursor=QTextCursor(self.document()); cursor.beginEditBlock()
            for y,line in enumerate(lines):
                if y: cursor.insertBlock()
                last=None; run=''
                def flush():
                    if not run or last is None: return
                    fg,bg,bold,italic,underline,reverse=last; fmt=QTextCharFormat()
                    a,b=self.color(fg),self.color(bg,True)
                    if reverse: a,b=b,a
                    fmt.setForeground(a); fmt.setBackground(b); fmt.setFontWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal); fmt.setFontItalic(italic); fmt.setFontUnderline(underline)
                    cursor.insertText(run,fmt)
                for x in range(self.screen.columns):
                    cell=line.get(x,self.screen.default_char); style=(cell.fg,cell.bg,cell.bold,cell.italics,cell.underscore,cell.reverse)
                    if style!=last: flush(); run=''; last=style
                    run+=cell.data
                flush()
            cursor.endEditBlock()
            if self.dead: cursor.insertBlock(); cursor.insertText('[Session ended — restart or close this tab]')
            # Place the Qt caret at the emulated cursor (selection is cleared on output).
            block=self.document().findBlockByNumber(len(history)+self.screen.cursor.y)
            if block.isValid():
                caret=QTextCursor(block); caret.setPosition(block.position()+min(self.screen.cursor.x,max(0,block.length()-1))); self.setTextCursor(caret); self.vt_caret=QTextCursor(caret); self.cursor_on=True
            bar.setValue(bar.maximum() if bottom else min(old,bar.maximum()))
        finally:
            self.viewport().setUpdatesEnabled(True)
            self.viewport().update()

    def send(self,data):
        if self.dead or self.stop.is_set(): return
        try:
            if self.win: self.win.write(data.decode('utf-8','replace'))
            elif self.fd is not None:
                # Nonblocking PTY: retain unsent bytes and retry on the GUI timer.
                self.pending=getattr(self,'pending',b'')+data; self.flush_input()
        except (OSError,EOFError): pass

    def flush_input(self):
        if self.fd is None or self.stop.is_set(): return
        try:
            n=os.write(self.fd,self.pending); self.pending=self.pending[n:]
        except BlockingIOError: pass
        except OSError: self.pending=b''; return
        if self.pending: QTimer.singleShot(15,self.flush_input)

    def event(self,event):
        if event.type()==QEvent.Type.ShortcutOverride:
            # Keep shell control keys out of editor-wide shortcuts.
            if event.key() not in (Qt.Key.Key_F11,) and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key()==Qt.Key.Key_QuoteLeft):
                event.accept(); return True
        return super().event(event)

    def keyPressEvent(self,e):
        k=e.key(); m=e.modifiers(); ctrl=bool(m & Qt.KeyboardModifier.ControlModifier); shift=bool(m & Qt.KeyboardModifier.ShiftModifier)
        if ctrl and shift and k==Qt.Key.Key_C: self.copy(); return
        if ctrl and shift and k==Qt.Key.Key_V: self.paste_shell(); return
        if ctrl and shift and k==Qt.Key.Key_T: self.studio.terminal_panel.add_session(); return
        if ctrl and shift and k==Qt.Key.Key_W: self.studio.terminal_panel.close_session(self.studio.terminal_panel.sessions.currentIndex()); return
        keys={Qt.Key.Key_Return:b'\r',Qt.Key.Key_Enter:b'\r',Qt.Key.Key_Backspace:b'\x7f',Qt.Key.Key_Tab:b'\t',Qt.Key.Key_Backtab:b'\x1b[Z',Qt.Key.Key_Escape:b'\x1b',Qt.Key.Key_Up:b'\x1b[A',Qt.Key.Key_Down:b'\x1b[B',Qt.Key.Key_Right:b'\x1b[C',Qt.Key.Key_Left:b'\x1b[D',Qt.Key.Key_Home:b'\x1b[H',Qt.Key.Key_End:b'\x1b[F',Qt.Key.Key_Delete:b'\x1b[3~',Qt.Key.Key_Insert:b'\x1b[2~',Qt.Key.Key_PageUp:b'\x1b[5~',Qt.Key.Key_PageDown:b'\x1b[6~'}
        if ctrl and Qt.Key.Key_A<=k<=Qt.Key.Key_Z: data=bytes([k-Qt.Key.Key_A+1])
        elif k in keys: data=keys[k]
        else: data=e.text().encode('utf-8')
        if data: self.send(data)
        e.accept()

    def paste_shell(self):
        value=QApplication.clipboard().text()
        if '\n' in value or '\r' in value:
            if QMessageBox.question(self,'Paste into shell','Paste multiple lines? Commands may execute immediately.')!=QMessageBox.StandardButton.Yes: return
        self.send(value.replace('\r\n','\n').replace('\n','\r').encode('utf-8'))

    def contextMenuEvent(self,event):
        from PySide6.QtWidgets import QMenu
        menu=QMenu(self); menu.addAction('Copy',self.copy); menu.addAction('Paste into shell',self.paste_shell); menu.exec(event.globalPos())

    def wheelEvent(self,e):
        super().wheelEvent(e)

    def shutdown(self):
        self.stop.set(); self.timer.stop(); self.blink_timer.stop(); self.dead=True
        if self.win:
            try: self.win.close(force=True)
            except Exception: pass
        if self.fd is not None:
            try:
                import signal
                group=os.tcgetpgrp(self.fd)
                if group>0 and group!=os.getpgrp(): os.killpg(group,signal.SIGHUP)
            except OSError: pass
            try: os.close(self.fd)
            except OSError: pass
            self.fd=None
        if self.pid:
            try:
                import signal
                os.kill(self.pid,signal.SIGHUP)
            except OSError: pass
            pid=self.pid; self.pid=None
            def reap():
                try:
                    for _ in range(20):
                        if os.waitpid(pid,os.WNOHANG)[0]: return
                        time.sleep(.05)
                    os.kill(pid,signal.SIGKILL); os.waitpid(pid,0)
                except OSError: pass
            threading.Thread(target=reap,daemon=True).start()


class TerminalPanel(QWidget):
    def __init__(self,studio):
        super().__init__(); self.studio=studio; self.serial=0
        layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        row=QHBoxLayout(); layout.addLayout(row)
        for label,fn in [('+',self.add_session),('Clear',self.clear_screen),('Restart',self.restart),('Settings',studio.terminal_settings)]:
            b=QToolButton(); b.setText(label); b.clicked.connect(fn); row.addWidget(b)
        row.addStretch(); self.sessions=QTabWidget(); self.sessions.setTabsClosable(True); self.sessions.setMovable(True); self.sessions.tabCloseRequested.connect(self.close_session); layout.addWidget(self.sessions)
    def ensure(self):
        if not self.sessions.count(): self.add_session()
    def add_session(self):
        e=self.studio.tabs.currentWidget(); cwd=Path(e.path).parent if e and e.path else Path.home()
        if not cwd.is_dir(): cwd=Path.home()
        self.serial+=1; session=TerminalSession(self.studio,cwd); self.sessions.addTab(session,'Shell '+str(self.serial)); self.sessions.setCurrentWidget(session); session.setFocus()
    def confirm(self,sessions):
        if any(not s.dead for s in sessions):
            return QMessageBox.question(self,'Close terminal','Live shell sessions may contain running commands. Terminate them?')==QMessageBox.StandardButton.Yes
        return True
    def close_session(self,index):
        s=self.sessions.widget(index)
        if s and self.confirm([s]): s.shutdown(); self.sessions.removeTab(index); s.deleteLater()
    def restart(self):
        i=self.sessions.currentIndex(); s=self.sessions.widget(i)
        if s and not self.confirm([s]): return
        if s: s.shutdown(); self.sessions.removeTab(i); s.deleteLater()
        self.add_session()
    def clear_screen(self):
        s=self.sessions.currentWidget()
        if s and s.screen: s.screen.reset(); s.render(); s.send(b'\x0c')
    def all_sessions(self): return [self.sessions.widget(i) for i in range(self.sessions.count())]


class Studio(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.system_palette = QPalette(app.palette())
        self.colors = {}
        self.counter = 0
        self.settings = QSettings("Tux Studio", "Tux Studio")
        self.language_options={k:self.settings.value("language/"+k,v,type=type(v)) for k,v in LANG_DEFAULTS.items()}
        self.mode = self.settings.value("themeMode", "System", type=str)
        if self.mode not in ("System", "Light", "Dark"):
            self.mode = "System"
        self.editor_options = {k:self.settings.value("editor/"+k,v,type=type(v)) for k,v in dict(completion=True,guides=True,current=True,wrap=True,whitespace=False,margin=120).items()}
        self.zoom_size = max(8, min(40, self.settings.value("editor/zoomSize", 13, type=int)))
        self.terminal_size = max(8,min(40,self.settings.value("terminal/size",13,type=int)))
        self.terminal_cursor_shape=self.settings.value("terminal/cursorShape","Vertical bar",type=str)
        if self.terminal_cursor_shape not in ("Vertical bar","Block","Underline"): self.terminal_cursor_shape="Vertical bar"
        self.terminal_cursor_blink=self.settings.value("terminal/cursorBlink",True,type=bool)
        self.terminal_color = self.settings.value("terminal/color","",type=str)
        if not QColor(self.terminal_color).isValid(): self.terminal_color=""
        self.last_dir = self.settings.value("lastDirectory", str(Path.home()), type=str)
        self.checking = False
        self.auto_enabled = self.settings.value('autoSaveEnabled', True, type=bool)
        self.auto_seconds = max(1, min(300, self.settings.value('autoSaveSeconds', 2, type=int)))
        self.recovery_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / 'recovery'
        self.recovery_dir.mkdir(parents=True, exist_ok=True)
        self.recovery_lock = QLockFile(str(self.recovery_dir / 'session.lock'))
        self.recovery_lock.setStaleLockTime(0)
        if not self.recovery_lock.tryLock(0):
            raise RuntimeError('Another Tux Studio session is using recovery storage.')
        self.setWindowTitle('Tux Studio — DEMO '+VERSION)
        self.setWindowIcon(penguin())
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(760, 480)
        screen = app.primaryScreen().availableGeometry()
        self.resize(min(1600, screen.width()), min(900, screen.height()))
        self.move(screen.center() - self.rect().center())
        root = QWidget(); root.setObjectName('root'); self.setCentralWidget(root)
        layout = QVBoxLayout(root); layout.setContentsMargins(1,1,1,1); layout.setSpacing(0)
        self.titlebar = TitleBar(self); layout.addWidget(self.titlebar)
        self.menu = QMenuBar(); self.menu.setNativeMenuBar(False); layout.addWidget(self.menu)
        self.actions = {}
        self.make_menus()
        toolbar = QWidget(); toolbar.setObjectName('toolbar'); toolbar.setFixedHeight(43)
        tools = QHBoxLayout(toolbar); tools.setContentsMargins(10,4,10,4); tools.setSpacing(6)
        for name, icon in [('New File','SP_FileIcon'),('Open File','SP_DialogOpenButton'),('Save','SP_DialogSaveButton'),('Undo','SP_ArrowBack'),('Redo','SP_ArrowForward')]:
            self.tool(tools,name,icon)
        tools.addStretch()
        target = QLabel('Current file'); target.setObjectName('muted'); tools.addWidget(target)
        self.tool(tools,'Run Current File','SP_MediaPlay'); self.tool(tools,'Stop Execution','SP_MediaStop')
        selector = QWidget(); selector.setObjectName('themeSelector')
        segments = QHBoxLayout(selector); segments.setContentsMargins(3,3,3,3); segments.setSpacing(2)
        self.theme_group = QButtonGroup(self); self.theme_group.setExclusive(True)
        self.theme_buttons = {}
        for mode in ('Light', 'Dark'):
            button = QToolButton(); button.setObjectName('themeSegment')
            button.setCheckable(True); button.setFixedSize(32,26); button.setIconSize(QSize(20,20))
            button.setAccessibleName(mode + ' theme'); button.setToolTip('Switch to ' + mode.lower() + ' theme')
            button.clicked.connect(lambda checked=False, m=mode: self.set_theme(m))
            self.theme_group.addButton(button); self.theme_buttons[mode] = button; segments.addWidget(button)
        tools.addWidget(selector)
        layout.addWidget(toolbar)
        self.splitter = QSplitter(Qt.Orientation.Horizontal); self.splitter.setChildrenCollapsible(False); self.splitter.setHandleWidth(5)
        self.tabs = QTabWidget(); self.tabs.setDocumentMode(True); self.tabs.setTabsClosable(True); self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab); self.tabs.currentChanged.connect(self.update_status)
        plus = QToolButton(); plus.setText('+'); plus.setToolTip('New file (Ctrl+N)'); plus.clicked.connect(self.new_tab); self.tabs.setCornerWidget(plus)
        left=QWidget(); left_layout=QVBoxLayout(left); left_layout.setContentsMargins(0,0,0,0); left_layout.setSpacing(0); left_layout.addWidget(self.tabs,1)
        self.search_panel=QWidget(); sl=QVBoxLayout(self.search_panel); sl.setContentsMargins(5,5,5,5)
        row=QHBoxLayout(); sl.addLayout(row); self.query=QLineEdit(); self.query.setPlaceholderText('Find'); row.addWidget(self.query,1)
        self.match_label=QLabel(); row.addWidget(self.match_label)
        self.case=QCheckBox('Aa'); self.whole=QCheckBox('Word'); self.regex=QCheckBox('.*')
        for cb in (self.case,self.whole,self.regex): row.addWidget(cb); cb.toggled.connect(self.refresh_search)
        for label,fn in [('↑',lambda:self.find_next(True)),('↓',self.find_next),('×',self.hide_search)]:
            button=QPushButton(label); row.addWidget(button); button.clicked.connect(fn)
        self.replace_row=QWidget(); rr=QHBoxLayout(self.replace_row); rr.setContentsMargins(0,0,0,0); sl.addWidget(self.replace_row)
        self.replacement=QLineEdit(); self.replacement.setPlaceholderText('Replace with'); rr.addWidget(self.replacement,1)
        for label,fn in [('Replace',lambda:self.replace_matches(False)),('Replace all',lambda:self.replace_matches(True))]:
            button=QPushButton(label); rr.addWidget(button); button.clicked.connect(fn)
        self.query.textChanged.connect(self.refresh_search); self.query.returnPressed.connect(self.find_next)
        self.tabs.currentChanged.connect(self.refresh_search); left_layout.addWidget(self.search_panel); self.search_panel.hide(); self.splitter.addWidget(left)
        self.terminals = QTabWidget(); self.terminals.setDocumentMode(True)
        console=QPlainTextEdit(); console.setObjectName('console'); console.setReadOnly(True); console.setFont(QFont('JetBrains Mono',11)); console.setPlainText('TUX Runtime\n\nReady. Press F5 to run the current TUX document.')
        self.terminals.addTab(console,'TUX Console'); self.runtime_console=console; self.runtime_thread=None; self.runtime_stop=threading.Event(); self.runtime_queue=queue.Queue(); self.runtime_timer=QTimer(self); self.runtime_timer.timeout.connect(self.poll_runtime); self.runtime_timer.start(50)
        self.runtime_input_queue=queue.Queue(); self.runtime_profile='Restricted'
        self.terminal_panel=TerminalPanel(self); self.terminals.addTab(self.terminal_panel,'System Terminal')
        self.terminals.currentChanged.connect(lambda i: self.terminal_panel.ensure() if i==1 else None)
        self.splitter.addWidget(self.terminals); self.splitter.setStretchFactor(0,3); self.splitter.setStretchFactor(1,2)
        layout.addWidget(self.splitter,1)
        self.status = QStatusBar(); self.status.setSizeGripEnabled(False); layout.addWidget(self.status)
        self.status.showMessage('Ready')
        self.auto_status = QLabel(); self.status.addPermanentWidget(self.auto_status)
        self.position = QLabel('Ln 1, Col 1'); self.status.addPermanentWidget(self.position)
        self.status.addPermanentWidget(QLabel('4 spaces · UTF-8 · '+VERSION))
        self.language_selector=QComboBox(); self.language_selector.addItems(['Automatic','TUX','Plain Text']); self.language_selector.currentTextChanged.connect(self.change_language); self.status.addPermanentWidget(self.language_selector)
        self.diagnostic_count=QToolButton(); self.diagnostic_count.setToolTip("Open TUX Diagnostics"); self.diagnostic_count.clicked.connect(lambda:self.inspect_language(True)); self.status.addPermanentWidget(self.diagnostic_count)
        self.status.addPermanentWidget(QSizeGrip(self))
        self.apply_theme(); self.new_tab()
        QTimer.singleShot(0, lambda: self.splitter.setSizes([int(self.splitter.width()*.6),int(self.splitter.width()*.4)]))
        hints = app.styleHints()
        if hasattr(hints,'colorSchemeChanged'): hints.colorSchemeChanged.connect(self.system_changed)
        app.installEventFilter(self)
        self.file_timer = QTimer(self)
        self.file_timer.timeout.connect(self.check_external)
        self.file_timer.start(1500)
        QTimer.singleShot(0, self.restore_documents)

    def eventFilter(self, obj, event):
        if event.type()==QEvent.Type.ToolTip and hasattr(self,"tabs") and self.language_options["tooltips"]:
            e=self.tabs.currentWidget()
            if e and obj is e.viewport() and hasattr(e,"language"):
                pos=e.cursorForPosition(event.pos()).position()
                for d in e.language.diagnostics():
                    if e.language.positions[d.start]<=pos<=e.language.positions[d.end]:
                        QToolTip.showText(event.globalPos(),self.diagnostic_text(d),obj); return True
        if event.type() == QEvent.Type.MouseButtonPress and isinstance(obj,QWidget) and obj.window() is self and not self.isMaximized() and not self.isFullScreen():
            if event.button() == Qt.MouseButton.LeftButton:
                point = self.mapFromGlobal(event.globalPosition().toPoint())
                edges = Qt.Edge(0)
                if point.x() < 5: edges |= Qt.Edge.LeftEdge
                elif point.x() >= self.width()-5: edges |= Qt.Edge.RightEdge
                if point.y() < 5: edges |= Qt.Edge.TopEdge
                elif point.y() >= self.height()-5: edges |= Qt.Edge.BottomEdge
                if edges and self.windowHandle() and self.windowHandle().startSystemResize(edges): return True
        return super().eventFilter(obj,event)

    def tool(self, layout, name, icon):
        b = QToolButton(); b.setDefaultAction(self.actions[name]); b.setIcon(self.style().standardIcon(getattr(QStyle.StandardPixmap,icon))); b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly); b.setIconSize(QSize(19,19)); b.setFixedSize(34,32); layout.addWidget(b)

    def make_menus(self):
        specs = {
            'File':[('New File','Ctrl+N',self.new_tab),('Open File','Ctrl+O',self.open_dialog),('Save','Ctrl+S',lambda: self.save_document()),('Save As','Ctrl+Shift+S',lambda: self.save_document(save_as=True)),('Save All','Ctrl+Alt+S',self.save_all),('Close Tab','Ctrl+W',lambda:self.close_tab(self.tabs.currentIndex())),('Exit','Ctrl+Q',self.close)],
            'Edit':[('Undo','Ctrl+Z',lambda:self.edit('undo')),('Redo','Ctrl+Shift+Z',lambda:self.edit('redo')),('Cut','Ctrl+X',lambda:self.edit('cut')),('Copy','Ctrl+C',lambda:self.edit('copy')),('Paste','Ctrl+V',lambda:self.edit('paste')),('Select All','Ctrl+A',lambda:self.edit('selectAll')),('Find','Ctrl+F',lambda:self.show_search(False)),('Replace','Ctrl+R',lambda:self.show_search(True)),('Next Match','F3',self.find_next),('Previous Match','Shift+F3',lambda:self.find_next(True)),('Go to Line','Ctrl+G',self.go_line),('Duplicate Line','Ctrl+D',lambda:self.line_action('duplicate')),('Delete Line','Ctrl+Y',lambda:self.line_action('delete')),('Move Line Up','Alt+Up',lambda:self.line_action('up')),('Move Line Down','Alt+Down',lambda:self.line_action('down'))],
            'View':[('Toggle Theme','',self.toggle_theme),('System Theme','',lambda:self.set_theme('System')),('Dark Theme','',lambda:self.set_theme('Dark')),('Light Theme','',lambda:self.set_theme('Light')),('Zoom In','Ctrl++',lambda:self.edit('zoomIn')),('Zoom Out','Ctrl+-',lambda:self.edit('zoomOut')),('Reset Zoom','Ctrl+0',lambda:self.edit('reset_zoom')),('Toggle Terminal','Ctrl+J',lambda:self.terminals.setVisible(not self.terminals.isVisible())),('Full Screen','F11',self.toggle_fullscreen)],
            'Code':[('Collapse / Expand Block','Ctrl+Num+-',self.fold_current),('Expand Block','Ctrl+Num++',self.expand_current),('Autocomplete','Ctrl+Space',None),('Check Syntax','',lambda:self.inspect_language(True))],
            'Run':[('Run Current File','F5',self.run_tux),('Stop Execution','Shift+F5',self.stop_tux),('Restart Execution','Ctrl+F5',self.run_tux)],
            'Tools':[('TUX Console','',lambda:self.show_terminal(0)),('System Terminal','Ctrl+`',lambda:self.show_terminal(1)),('Diagnostics','',lambda:self.inspect_language(True)),('TUX Token Inspector','',lambda:self.inspect_language(False)),('TUX AST Inspector','',self.inspect_ast),('TUX Symbol Inspector','',self.inspect_symbols)],
            'Settings':[('Automatic Saving','',self.toggle_auto),('Auto-save Interval','',self.set_auto_interval),('Editor','',self.editor_settings),('Terminal','',self.terminal_settings),('TUX Language','',self.language_settings),('Runtime Permissions','',self.runtime_permissions),('Keyboard Shortcuts','',self.shortcut_settings)],
            'Help':[('Language Reference','',None),('About Tux Studio','',self.about)]}
        self.line_shortcuts = ('Go to Line','Duplicate Line','Delete Line','Move Line Up','Move Line Down')
        self.shortcut_defaults = {}
        for title, entries in specs.items():
            menu = self.menu.addMenu(title)
            advanced = menu.addMenu('Advanced Developer Tools') if title=='Tools' else None
            for name, shortcut, callback in entries:
                action = QAction(name,self); self.actions[name]=action
                if shortcut: action.setShortcut(shortcut)
                if name=='Zoom In': action.setShortcuts([QKeySequence('Ctrl++'), QKeySequence('Ctrl+=')])
                if name=='Replace': action.setShortcuts([QKeySequence('Ctrl+R'),QKeySequence('Ctrl+H')])
                if callback: action.triggered.connect(callback)
                else: action.setEnabled(False); action.setToolTip('Not implemented in this demo')
                if name in self.line_shortcuts:
                    self.addAction(action)
                    self.shortcut_defaults[name]=shortcut
                    action.setShortcut(QKeySequence(str(self.settings.value('keymap/'+name,shortcut)),QKeySequence.SequenceFormat.PortableText))
                elif advanced is not None and name.endswith('Inspector'):
                    advanced.addAction(action)
                else: menu.addAction(action)
                if name == "Automatic Saving":
                    action.setCheckable(True); action.setChecked(self.auto_enabled)

    def shortcut_settings(self):
        dialog=QDialog(self); dialog.setWindowTitle('Keyboard Shortcuts'); layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel('Customize line editing shortcuts. Clear a shortcut to disable it.'))
        form=QFormLayout(); layout.addLayout(form); fields={}
        for name in self.line_shortcuts:
            field=QKeySequenceEdit(self.actions[name].shortcut()); fields[name]=field; form.addRow(name,field)
        reset=QPushButton('Restore Defaults'); layout.addWidget(reset)
        def restore():
            for name,field in fields.items(): field.setKeySequence(QKeySequence(self.shortcut_defaults[name]))
        reset.clicked.connect(restore)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel); layout.addWidget(buttons)
        def save():
            used=[seq for name,action in self.actions.items() if name not in fields and action.isEnabled() for seq in action.shortcuts() if not seq.isEmpty()]
            for name,field in fields.items():
                seq=field.keySequence()
                if seq.isEmpty(): continue
                if any(seq.matches(other)!=QKeySequence.SequenceMatch.NoMatch or other.matches(seq)!=QKeySequence.SequenceMatch.NoMatch for other in used):
                    QMessageBox.warning(dialog,'Shortcut conflict','Choose a different shortcut for '+name); return
                used.append(seq)
            for name,field in fields.items():
                seq=field.keySequence(); self.actions[name].setShortcut(seq); self.settings.setValue('keymap/'+name,seq.toString(QKeySequence.SequenceFormat.PortableText))
            self.settings.sync(); dialog.accept()
        buttons.accepted.connect(save); buttons.rejected.connect(dialog.reject); dialog.exec()

    def runtime_permissions(self):
        if self.runtime_thread and self.runtime_thread.is_alive():
            self.status.showMessage('Stop execution before changing profile',3000); return
        profile,ok=QInputDialog.getItem(self,'Runtime Permissions','Profile label (all currently enforce Restricted policy):',['Restricted','Project','Trusted','Testing'],['Restricted','Project','Trusted','Testing'].index(self.runtime_profile),False)
        if ok:self.runtime_profile=profile
    def permission_review(self,payload):
        profile,entries=payload
        dialog=QDialog(self); dialog.setWindowTitle('TUX Permission Review'); dialog.resize(620,400)
        layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel('Profile: '+profile+' — Restricted policy remains enforced.'))
        view=QPlainTextEdit(); view.setReadOnly(True)
        view.setPlainText('\n\n'.join(f'{mode}: {name} {args!r}\nStatus: {status}\nReason: {reason}' for mode,name,args,reason,status in entries))
        layout.addWidget(view)
        layout.addWidget(QLabel('Continue may offer explicit read-only file selection; other restricted capabilities remain denied.'))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return False
        grants={}
        if not sys.platform.startswith('linux'):return grants
        for mode,name,args,reason,status in entries:
            if name!='files.read' or len(args)!=1 or len(grants)>=10:continue
            key=args[0]
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',key) or key in ('.','..'):continue
            if self.runtime_stop.is_set():return False
            answer=QMessageBox.question(self,'Select a read-only file','Allow a one-run text snapshot for alias '+key+'? You choose the actual file.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:continue
            path,_=QFileDialog.getOpenFileName(self,'Select file for '+key)
            if not path:continue
            try:grants[key]=tux_read_selected_file(path)
            except (OSError,ValueError) as exc:QMessageBox.warning(self,'File unavailable',str(exc))
        return grants
    def poll_runtime(self):
        if getattr(self,"runtime_poll_busy",False):return
        self.runtime_poll_busy=True
        try:self._poll_runtime()
        finally:self.runtime_poll_busy=False
    def _poll_runtime(self):
        chunks=[]
        while True:
            try: chunks.append(self.runtime_queue.get_nowait())
            except queue.Empty: break
        prompts=[x[1] for x in chunks if isinstance(x,tuple)]; chunks=[x for x in chunks if isinstance(x,str)]
        if chunks:
            self.runtime_console.moveCursor(QTextCursor.MoveOperation.End)
            self.runtime_console.insertPlainText(''.join(chunks))
            self.runtime_console.ensureCursorVisible()
        for prompt in prompts:
            if self.runtime_stop.is_set():continue
            mode,prompt=prompt if isinstance(prompt,tuple) else ('input',prompt)
            if mode=='permissionReview':
                value=self.permission_review(prompt); ok=True
            elif mode=='confirm':
                answer=QMessageBox.question(self,'TUX Confirmation',prompt or 'Continue?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No|QMessageBox.StandardButton.Cancel)
                ok=answer in (QMessageBox.StandardButton.Yes,QMessageBox.StandardButton.No)
                value='true' if answer==QMessageBox.StandardButton.Yes else 'false'
            else:
                echo=QLineEdit.EchoMode.Password if mode=='inputPassword' else QLineEdit.EchoMode.Normal
                value,ok=QInputDialog.getText(self,'TUX Console Input',prompt or 'Enter input:',echo)
            if not ok:self.runtime_stop.set()
            else:self.runtime_input_queue.put(value)
    def stop_tux(self):
        self.runtime_stop.set()
    def run_tux(self):
        if self.runtime_thread and self.runtime_thread.is_alive():
            self.status.showMessage('Execution already running; stop it first',3000); return
        e=self.tabs.currentWidget()
        if not e: return
        self.poll_runtime(); self.runtime_console.clear(); self.show_terminal(0)
        source=e.toPlainText(); self.runtime_stop=threading.Event()
        self.runtime_input_queue=queue.Queue()
        profile=self.runtime_profile
        self.runtime_thread=threading.Thread(target=tux_process_run,args=(source,profile,self.runtime_stop,self.runtime_queue.put,self.runtime_input_queue),daemon=True)
        self.runtime_thread.start()

    def change_language(self,mode):
        e=self.tabs.currentWidget()
        if e and hasattr(e,'language'): e.language.mode=mode; e.language.analyze()

    def diagnostic_text(self,d):
        o=self.language_options; text=d.code+' — '+d.message
        if o['detail']!='Compact' and o['suggestions'] and d.suggestion: text+='\nSuggestion: '+d.suggestion
        if o['detail']=='Learning': text+='\nParser diagnostics identify invalid grammatical structure.' if '-PAR-' in d.code else '\nSemantic diagnostics check declarations and types.' if '-SEM-' in d.code else '\nLexical diagnostics identify invalid source characters or literals before parsing.'
        return text

    def inspect_language(self,diagnostics=False):
        e=self.tabs.currentWidget()
        if not e: return
        lang=e.language; dialog=QDialog(self); dialog.setWindowTitle('TUX Diagnostics' if diagnostics else 'TUX Token Inspector'); dialog.resize(850,480); layout=QVBoxLayout(dialog)
        summary=QLabel(); layout.addWidget(summary); filterbox=QComboBox(); layout.addWidget(filterbox); table=QTableWidget(); table.setColumnCount(4); table.setHorizontalHeaderLabels(['Code / Token','Message / Category','Line','Column']); table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); layout.addWidget(table); rows=[]
        def refresh():
            lang.analyze(synchronous=True); selected=filterbox.currentText(); filterbox.blockSignals(True); filterbox.clear(); filterbox.addItem('All'); filterbox.addItems(sorted({t.kind for t in lang.result.tokens}) if not diagnostics else ['Errors','Warnings']); filterbox.setCurrentText(selected); filterbox.blockSignals(False); populate()
        def populate():
            rows.clear(); selected=filterbox.currentText()
            if diagnostics:
                ds=lang.diagnostics(manual=True)
                summary.setText(('Analysis failed: '+lang.last_error) if lang.last_error else ('Plain Text mode — select TUX to analyze' if not lang.enabled() else f"{sum('-E-' in d.code for d in ds)} errors · {sum('-W-' in d.code for d in ds)} warnings"))
            else: summary.setText(f'{len(lang.result.tokens)} tokens')
            if diagnostics:
                for d in lang.diagnostics(manual=True):
                    if selected=='Errors' and '-E-' not in d.code or selected=='Warnings' and '-W-' not in d.code: continue
                    line=lang.source.count('\n',0,d.start)+1; col=d.start-lang.source.rfind('\n',0,d.start); rows.append((d.start,d.end,[d.code,self.diagnostic_text(d),str(line),str(col)]))
            else:
                for t in lang.result.tokens:
                    if selected!='All' and selected!=t.kind: continue
                    rows.append((t.start,t.end,[repr(t.text),t.kind,str(t.line),str(t.column)]))
            table.setRowCount(len(rows))
            for i,(_,__,values) in enumerate(rows):
                for j,v in enumerate(values):
                    item=QTableWidgetItem(v)
                    if diagnostics and j in (0,1):
                        dark=e.colors.get('dark',False); warning='-W-' in values[0]
                        item.setForeground(QColor(('#e5b567' if warning else '#ff6b68') if dark else ('#986400' if warning else '#c62828')))
                    table.setItem(i,j,item)
            table.horizontalHeader().setStretchLastSection(True)
        filterbox.currentTextChanged.connect(lambda _:populate()); table.cellClicked.connect(lambda r,c:lang.navigate(*rows[r][:2]) if 0<=r<len(rows) else None); table.cellDoubleClicked.connect(lambda r,c:dialog.accept() if 0<=r<len(rows) else None); buttons=QHBoxLayout(); layout.addLayout(buttons)
        for label,fn in [('Refresh',refresh),('Copy',lambda:QApplication.clipboard().setText('\n'.join('\t'.join(r[2]) for r in rows))),('Close',dialog.accept)]:
            b=QPushButton(label); b.clicked.connect(fn); buttons.addWidget(b)
        refresh(); dialog.exec()

    def inspect_symbols(self):
        e=self.tabs.currentWidget()
        if not e: return
        lang=e.language; dialog=QDialog(self); dialog.setWindowTitle('TUX Symbol Inspector'); dialog.resize(760,460)
        layout=QVBoxLayout(dialog); summary=QLabel(); layout.addWidget(summary)
        tree=QTreeWidget(); tree.setHeaderLabels(['Name','Declared type','Binding','Scope depth','Line']); layout.addWidget(tree)
        def refresh():
            lang.analyze(synchronous=True); tree.clear()
            analyzer=getattr(lang,'semantic_analyzer',None); symbols=getattr(analyzer,'symbols',[])
            summary.setText(f'{len(symbols)} symbols (initial semantic coverage)')
            for symbol in symbols[:10000]:
                item=QTreeWidgetItem([symbol.name,symbol.type_name,'Constant' if symbol.constant else 'Binding',str(symbol.depth),str(lang.source.count('\n',0,symbol.start)+1)])
                item.setData(0,Qt.ItemDataRole.UserRole,(symbol.start,symbol.end)); tree.addTopLevelItem(item)
        def navigate(item,column):
            if lang.source==e.toPlainText(): lang.navigate(*item.data(0,Qt.ItemDataRole.UserRole))
        tree.itemClicked.connect(navigate)
        buttons=QHBoxLayout(); layout.addLayout(buttons)
        for label,fn in [('Refresh',refresh),('Copy selected',lambda:QApplication.clipboard().setText(' | '.join(tree.currentItem().text(i) for i in range(5))) if tree.currentItem() else None),('Close',dialog.accept)]:
            b=QPushButton(label); b.clicked.connect(fn); buttons.addWidget(b)
        refresh(); dialog.exec()

    def inspect_ast(self):
        e=self.tabs.currentWidget()
        if not e: return
        lang=e.language; dialog=QDialog(self); dialog.setWindowTitle('TUX AST Inspector'); dialog.resize(850,520); layout=QVBoxLayout(dialog)
        summary=QLabel(); layout.addWidget(summary); tree=QTreeWidget(); tree.setHeaderLabels(['Node','Value','Source offsets']); layout.addWidget(tree); nodes={}
        def refresh():
            lang.analyze(synchronous=True); tree.clear(); nodes.clear(); result=getattr(lang,'parse_result',None)
            if not result or lang.last_error: summary.setText('No current AST available'); return
            summary.setText(f'{len(result.diagnostics)} parser diagnostics — lexical errors prevent parsing')
            stack=[(None,result.root)]
            while stack and len(nodes)<10000:
                parent,n=stack.pop(); item=QTreeWidgetItem([n.kind,n.value,str(n.start)+'–'+str(n.end)]); item.setData(0,Qt.ItemDataRole.UserRole,n.node_id); nodes[n.node_id]=n
                if parent is None: tree.addTopLevelItem(item)
                else: parent.addChild(item)
                stack.extend((item,c) for c in reversed(n.children))
            tree.expandToDepth(2)
            if stack: summary.setText(summary.text()+' — display limited to 10,000 nodes')
        def navigate(item,column):
            n=nodes.get(item.data(0,Qt.ItemDataRole.UserRole))
            if n: lang.navigate(n.start,n.end)
        def export_json():
            result=getattr(lang,'parse_result',None)
            if not result or lang.last_error or lang.source!=e.toPlainText():
                QMessageBox.warning(dialog,'AST export','Refresh the AST before exporting.'); return
            path,_=QFileDialog.getSaveFileName(dialog,'Export AST','ast.json','JSON (*.json)')
            if not path: return
            try:
                payload=tux_ast_export(result)
                Path(path).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
            except Exception as exc: QMessageBox.warning(dialog,'AST export',str(exc))
        tree.itemClicked.connect(navigate); buttons=QHBoxLayout(); layout.addLayout(buttons)
        for label,fn in [('Export JSON',export_json),('Refresh',refresh),('Expand',tree.expandAll),('Collapse',tree.collapseAll),('Copy selected',lambda:QApplication.clipboard().setText(' | '.join(tree.currentItem().text(i) for i in range(3))) if tree.currentItem() else None),('Close',dialog.accept)]:
            b=QPushButton(label); b.clicked.connect(fn); buttons.addWidget(b)
        refresh(); dialog.exec()

    def language_settings(self):
        d=QDialog(self); d.setWindowTitle('TUX Language Settings'); layout=QFormLayout(d); controls={}
        for k,v in LANG_DEFAULTS.items():
            if isinstance(v,bool):
                c=QCheckBox(); c.setChecked(self.language_options[k]); controls[k]=c; layout.addRow(k.capitalize(),c)
        delay=QSpinBox(); delay.setRange(100,2000); delay.setValue(self.language_options['delay']); layout.addRow('Analysis delay (ms)',delay)
        detail=QComboBox(); detail.addItems(['Compact','Standard','Learning']); detail.setCurrentText(self.language_options['detail']); layout.addRow('Diagnostic detail',detail)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel); layout.addRow(buttons); buttons.accepted.connect(d.accept); buttons.rejected.connect(d.reject)
        if d.exec():
            self.language_options.update({k:c.isChecked() for k,c in controls.items()}); self.language_options.update(delay=delay.value(),detail=detail.currentText())
            for k,v in self.language_options.items(): self.settings.setValue('language/'+k,v)
            for i in range(self.tabs.count()): self.tabs.widget(i).language.analyze()

    def fold_current(self):
        e=self.tabs.currentWidget()
        if e: e.toggle_fold(e.textCursor().blockNumber())

    def expand_current(self):
        e=self.tabs.currentWidget()
        if e and e.textCursor().blockNumber() in e.collapsed: e.toggle_fold(e.textCursor().blockNumber())

    def editor_settings(self):
        d=QDialog(self); d.setWindowTitle('Editor Settings'); layout=QFormLayout(d); controls={}
        for key,label in [('completion','Bracket and quote completion'),('guides','Indentation guides'),('current','Current line highlighting'),('wrap','Word wrap'),('whitespace','Show whitespace')]:
            cb=QCheckBox(); cb.setChecked(self.editor_options[key]); layout.addRow(label,cb); controls[key]=cb
        margin=QSpinBox(); margin.setRange(0,300); margin.setSpecialValueText('Disabled'); margin.setValue(self.editor_options['margin']); layout.addRow('Right margin',margin)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel); layout.addRow(buttons); buttons.accepted.connect(d.accept); buttons.rejected.connect(d.reject)
        if d.exec():
            self.editor_options.update({k:v.isChecked() for k,v in controls.items()}); self.editor_options['margin']=margin.value()
            for k,v in self.editor_options.items(): self.settings.setValue('editor/'+k,v)
            for i in range(self.tabs.count()): self.tabs.widget(i).apply_options(self.editor_options)

    def line_action(self,action):
        e=self.tabs.currentWidget()
        if e: e.line_action(action)

    def go_line(self):
        e=self.tabs.currentWidget()
        if not e: return
        n,ok=QInputDialog.getInt(self,'Go to Line','Line:',e.textCursor().blockNumber()+1,1,e.blockCount())
        if ok:
            c=QTextCursor(e.document().findBlockByNumber(n-1)); e.setTextCursor(c); e.centerCursor()

    def show_search(self,replace=False):
        self.search_panel.show(); self.replace_row.setVisible(replace); self.query.setFocus(); self.query.selectAll(); self.refresh_search()

    def hide_search(self):
        self.search_panel.hide(); self.refresh_search(); e=self.tabs.currentWidget()
        if e: e.setFocus()

    def search_matches(self):
        e=self.tabs.currentWidget(); q=self.query.text()
        if not e or not q: return []
        pattern=q if self.regex.isChecked() else re.escape(q)
        if self.whole.isChecked(): pattern=r'\b(?:'+pattern+r')\b'
        return list(re.finditer(pattern,e.toPlainText(),0 if self.case.isChecked() else re.IGNORECASE))

    def refresh_search(self,*_):
        if not hasattr(self,'search_panel'): return
        e=self.tabs.currentWidget()
        for i in range(self.tabs.count()):
            ed=self.tabs.widget(i); ed.search_ranges=[]
            if ed is not e: ed.highlight()
        if not e: return
        try:
            matches=self.search_matches() if not self.search_panel.isHidden() else []; text=e.toPlainText()
            e.search_ranges=[(len(text[:m.start()].encode('utf-16-le'))//2,len(text[:m.end()].encode('utf-16-le'))//2) for m in matches]; self.match_label.setText(str(len(matches))+' matches')
        except re.error: self.match_label.setText('Invalid regex')
        e.highlight()

    def find_next(self,back=False):
        if self.search_panel.isHidden(): self.show_search(False)
        e=self.tabs.currentWidget()
        if not e or not e.search_ranges: return
        c=e.textCursor(); ranges=e.search_ranges
        a,b=next(((a,b) for a,b in reversed(ranges) if a<c.selectionStart()),ranges[-1]) if back else next(((a,b) for a,b in ranges if a>=c.selectionEnd() and (a,b)!=(c.selectionStart(),c.selectionEnd())),ranges[0])
        c.setPosition(a); c.setPosition(b,QTextCursor.MoveMode.KeepAnchor); e.setTextCursor(c); e.centerCursor()

    def replace_matches(self,all_matches):
        e=self.tabs.currentWidget()
        if not e: return
        try:
            matches=self.search_matches(); text=e.toPlainText(); edits=[]
            for m in matches:
                a=len(text[:m.start()].encode('utf-16-le'))//2; b=len(text[:m.end()].encode('utf-16-le'))//2
                if all_matches or (a,b)==(e.textCursor().selectionStart(),e.textCursor().selectionEnd()): edits.append((a,b,m.expand(self.replacement.text()) if self.regex.isChecked() else self.replacement.text()))
            if not edits: self.find_next(); return
        except re.error: return
        c=e.textCursor(); c.beginEditBlock()
        for a,b,value in reversed(edits): c.setPosition(a); c.setPosition(b,QTextCursor.MoveMode.KeepAnchor); c.insertText(value)
        c.endEditBlock(); self.refresh_search()

    def edit(self, method):
        e = self.tabs.currentWidget()
        if e: getattr(e,method)(); e.update_gutter(); e.highlight()

    def set_editor_zoom(self, size):
        self.zoom_size = max(8, min(40, int(size)))
        self.settings.setValue("editor/zoomSize", self.zoom_size)
        self.settings.sync()
        for i in range(self.tabs.count()):
            self.tabs.widget(i).set_zoom_size(self.zoom_size)

    def new_tab(self):
        self.counter += 1
        e = Editor(self.colors)
        e.zoom_callback = self.set_editor_zoom
        e.set_zoom_size(self.zoom_size)
        e.apply_options(self.editor_options)
        e.textChanged.connect(self.refresh_search)
        e.path = None
        e.language=TuxEditorLanguage(e,self)
        e.viewport().setMouseTracking(True); e.viewport().installEventFilter(self)
        e.disk_hash = None
        e.seen_hash = None
        e.bom = False
        e.newline = "\n"
        e.files_dropped = self.open_paths
        e.recovery_id = uuid.uuid4().hex
        e.loading = False
        e.auto_state = 'Saved'
        e.auto_timer = QTimer(e); e.auto_timer.setSingleShot(True)
        e.auto_timer.timeout.connect(lambda: self.auto_save(e))
        e.textChanged.connect(lambda: self.schedule_auto(e))
        e.setProperty('filename','Untitled.tux' if self.counter==1 else f'Untitled-{self.counter}.tux')
        index = self.tabs.addTab(e,e.property('filename'))
        e.document().modificationChanged.connect(lambda _: self.update_tab(e))
        e.cursorPositionChanged.connect(self.update_status)
        self.tabs.setCurrentIndex(index); e.setFocus(); e.language.analyze(); self.update_status()

    def update_tab(self,e):
        index=self.tabs.indexOf(e)
        if index>=0:
            self.tabs.setTabText(index,e.property('filename')+(' *' if e.document().isModified() else ''))
            self.tabs.setTabToolTip(index, str(e.path) if e.path else 'Unsaved document')
        if hasattr(e,"language"): e.language.schedule()
        self.update_status()

    def remember_directory(self, path):
        self.last_dir = str(Path(path).parent)
        self.settings.setValue('lastDirectory', self.last_dir)

    def file_error(self, path, exc):
        if isinstance(exc, FileNotFoundError): code = 'FILE-001'
        elif isinstance(exc, PermissionError): code = 'FILE-002'
        elif isinstance(exc, UnicodeError): code = 'FILE-004'
        elif getattr(exc, 'errno', None) == errno.ENOSPC: code = 'FILE-007'
        else: code = 'FILE-005'
        QMessageBox.warning(self, code + ' — File operation failed',
                            f'{path}\n\n{exc}\n\nCheck the file, its encoding, available disk space and permissions.')

    def dialog(self, saving=False, name=''):
        d = QFileDialog(self, 'Save document' if saving else 'Open documents', self.last_dir)
        d.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        d.setNameFilters(['TUX files (*.tux)', 'All files (*)'])
        d.setAcceptMode(QFileDialog.AcceptMode.AcceptSave if saving else QFileDialog.AcceptMode.AcceptOpen)
        d.setFileMode(QFileDialog.FileMode.AnyFile if saving else QFileDialog.FileMode.ExistingFiles)
        if saving:
            d.setDefaultSuffix('tux')
            d.selectFile(name)
        return d.selectedFiles() if d.exec() else []

    def open_dialog(self):
        self.open_paths(self.dialog())

    @staticmethod
    def read_text(path):
        raw = path.read_bytes()
        text = raw.decode('utf-8-sig')
        if any(ord(ch) < 32 and ch not in '\t\n\r\f' for ch in text):
            raise UnicodeError('This file contains binary or unsupported control characters.')
        return text, hashlib.sha256(raw).digest(), raw.startswith(b'\xef\xbb\xbf'), '\r\n' if b'\r\n' in raw else '\n'

    def find_path(self, path):
        for i in range(self.tabs.count()):
            e = self.tabs.widget(i)
            if e.path is not None and os.path.normcase(str(e.path)) == os.path.normcase(str(path)):
                return e
        return None

    def load_document(self, e, path, data):
        text, digest, bom, newline = data
        e.path, e.disk_hash, e.seen_hash = path, digest, digest
        e.bom, e.newline = bom, newline
        e.setProperty('filename', path.name)
        e.auto_timer.stop(); e.loading = True
        try: e.setPlainText(text)
        finally: e.loading = False
        e.document().setModified(False)
        self.clear_snapshot(e); e.auto_state = "Saved"
        self.update_tab(e)

    def open_paths(self, paths):
        for name in paths:
            try:
                path = Path(name).resolve()
                existing = self.find_path(path)
                if existing is not None:
                    self.tabs.setCurrentWidget(existing)
                    continue
                data = self.read_text(path)
                e = self.tabs.currentWidget()
                if e is None or e.path is not None or e.document().isModified() or e.toPlainText():
                    self.new_tab()
                    e = self.tabs.currentWidget()
                self.load_document(e, path, data)
                self.remember_directory(path)
                self.status.showMessage('Opened ' + path.name, 4000)
            except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
                self.file_error(name, exc)

    @staticmethod
    def fingerprint(path):
        try:
            return hashlib.sha256(path.read_bytes()).digest()
        except FileNotFoundError:
            return None

    def save_document(self, e=None, save_as=False, automatic=False):
        if e is None: e = self.tabs.currentWidget()
        if e is None: return False
        path = e.path
        try:
            if save_as or path is None:
                if automatic: return False
                names = self.dialog(True, str(path) if path else e.property('filename'))
                if not names: return False
                path = Path(names[0]).resolve()
            other = self.find_path(path)
            if other is not None and other is not e:
                QMessageBox.warning(self, 'File already open', 'Close the other document before saving to this path.')
                return False
            if path == e.path and self.fingerprint(path) != e.disk_hash:
                if automatic: return False
                if QMessageBox.question(self, 'FILE-006 — External change',
                    f'{path} has changed or disappeared on disk. Overwrite with your editor content?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
                    return False
            text = e.toPlainText().replace('\n', e.newline)
            raw = text.encode('utf-8-sig' if e.bom else 'utf-8')
            f = QSaveFile(str(path))
            f.setDirectWriteFallback(False)
            if not f.open(QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(f.errorString())
            if f.write(raw) != len(raw):
                error = f.errorString(); f.cancelWriting(); raise OSError(error)
            if automatic and self.fingerprint(path) != e.disk_hash:
                f.cancelWriting(); return False
            if not f.commit(): raise OSError(f.errorString())
            e.path = path
            e.disk_hash = e.seen_hash = hashlib.sha256(raw).digest()
            e.setProperty('filename', path.name)
            e.document().setModified(False)
            e.auto_timer.stop(); self.clear_snapshot(e); e.auto_state = 'Saved'
            self.update_tab(e)
            if not automatic: self.remember_directory(path)
            self.status.showMessage('Saved ' + path.name, 4000)
            return True
        except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
            if not automatic: self.file_error(path, exc)
            return False

    def save_all(self):
        for i in range(self.tabs.count()):
            e = self.tabs.widget(i)
            if (e.document().isModified() or e.seen_hash != e.disk_hash) and not self.save_document(e):
                self.tabs.setCurrentWidget(e)
                return False
        return True

    def check_external(self):
        if self.checking or QApplication.activeModalWidget() is not None: return
        self.checking = True
        try:
            for i in range(self.tabs.count()):
                e = self.tabs.widget(i)
                if e.path is None: continue
                try: digest = self.fingerprint(e.path)
                except OSError: continue
                if digest == e.seen_hash: continue
                e.seen_hash = digest
                if digest == e.disk_hash: continue
                e.auto_timer.stop(); self.write_snapshot(e); e.auto_state = "External change — auto-save paused"; self.update_status()
                if digest is None:
                    QMessageBox.warning(self, 'FILE-006 — File removed', f'{e.path} is missing. Your editor content is retained.')
                    continue
                answer = QMessageBox.question(self, 'FILE-006 — External change',
                    f'{e.path} changed on disk. Reload it? Reloading discards any unsaved editor changes. Choose No to keep your content.',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if answer == QMessageBox.StandardButton.Yes:
                    try: self.load_document(e, e.path, self.read_text(e.path))
                    except (OSError, UnicodeError) as exc: self.file_error(e.path, exc)
        finally:
            self.checking = False

    def confirm_close(self, e):
        if not e.document().isModified() and e.seen_hash == e.disk_hash: return True
        answer = QMessageBox.question(self, 'Unsaved changes',
            f'{e.property("filename")} contains unsaved changes. Save before closing?',
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Save: return self.save_document(e)
        return answer == QMessageBox.StandardButton.Discard

    def close_tab(self,index):
        e = self.tabs.widget(index)
        if e is None or not self.confirm_close(e): return
        e.auto_timer.stop(); self.clear_snapshot(e)
        self.tabs.removeTab(index); e.deleteLater()
        if not self.tabs.count(): self.new_tab()

    def closeEvent(self,event):
        sessions=self.terminal_panel.all_sessions()
        if not self.terminal_panel.confirm(sessions): event.ignore(); return
        for i in range(self.tabs.count()):
            if not self.confirm_close(self.tabs.widget(i)):
                event.ignore(); return
        for i in range(self.tabs.count()):
            e = self.tabs.widget(i); e.auto_timer.stop(); self.clear_snapshot(e)
        self.runtime_stop.set()
        if self.runtime_thread: self.runtime_thread.join(timeout=2)
        for session in sessions: session.shutdown()
        self.recovery_lock.unlock()
        event.accept()

    def update_status(self,*_):
        e=self.tabs.currentWidget()
        if e:
            self.auto_status.setText(('✓ ' if e.auto_state == 'Saved' else '◷ ' if e.auto_state == 'Waiting' else '◆ ') + (e.auto_state if self.auto_enabled else 'Auto-save disabled · ' + e.auto_state))
            cursor=e.textCursor(); self.position.setText(f'Ln {cursor.blockNumber()+1}, Col {cursor.positionInBlock()+1}')
            if hasattr(e,"language"):
                self.language_selector.blockSignals(True); self.language_selector.setCurrentText(e.language.mode); self.language_selector.blockSignals(False)
                self.diagnostic_count.setText(e.language.status_text() if self.language_options["counters"] else "")
            self.titlebar.filename.setText('— '+e.property('filename')+(' *' if e.document().isModified() else ''))

    def toggle_auto(self, enabled):
        self.auto_enabled = enabled
        self.settings.setValue('autoSaveEnabled', enabled)
        for i in range(self.tabs.count()):
            e = self.tabs.widget(i)
            e.auto_timer.stop()
            if e.document().isModified(): self.schedule_auto(e)
        self.update_status()

    def set_auto_interval(self):
        seconds, ok = QInputDialog.getInt(self, 'Auto-save interval', 'Seconds of inactivity:', self.auto_seconds, 1, 300)
        if ok:
            self.auto_seconds = seconds
            self.settings.setValue('autoSaveSeconds', seconds)
            for i in range(self.tabs.count()):
                e = self.tabs.widget(i)
                if e.document().isModified(): self.schedule_auto(e)

    def schedule_auto(self, e):
        if e.loading: return
        e.auto_state = 'Waiting' if self.auto_enabled else 'Unsaved changes'
        # Recovery protection remains enabled even when original-file auto-save is off.
        e.auto_timer.start(self.auto_seconds * 1000)
        self.update_status()

    def snapshot_path(self, e):
        return self.recovery_dir / (e.recovery_id + '.json')

    def clear_snapshot(self, e):
        try: self.snapshot_path(e).unlink(missing_ok=True)
        except OSError as exc:
            self.status.showMessage('Recovery cleanup failed: ' + str(exc), 8000)

    def write_snapshot(self, e):
        data = dict(name=e.property('filename'), path=str(e.path) if e.path else None,
                    text=e.toPlainText(), cursor=e.textCursor().position(),
                    digest=e.disk_hash.hex() if e.disk_hash else None, bom=e.bom,
                    newline=e.newline, modified=e.document().isModified(), timestamp=time.time())
        try:
            raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
            f = QSaveFile(str(self.snapshot_path(e))); f.setDirectWriteFallback(False)
            if not f.open(QIODevice.OpenModeFlag.WriteOnly): raise OSError(f.errorString())
            if f.write(raw) != len(raw):
                f.cancelWriting(); raise OSError('Incomplete recovery write')
            if not f.commit(): raise OSError(f.errorString())
            return True
        except (OSError, UnicodeError) as exc:
            self.status.showMessage('Recovery failed: ' + str(exc), 8000)
            return False

    def auto_save(self, e):
        if self.tabs.indexOf(e) < 0: return
        if self.checking or QApplication.activeModalWidget() is not None:
            e.auto_timer.start(500); return
        if not e.document().isModified() and e.seen_hash == e.disk_hash:
            self.clear_snapshot(e); e.auto_state = 'Saved'; self.update_status(); return
        if not self.write_snapshot(e):
            e.auto_state = 'Recovery failed'; self.update_status(); return
        e.auto_state = 'Recovery saved'
        if self.auto_enabled and e.path is not None:
            try:
                if self.fingerprint(e.path) != e.disk_hash:
                    e.auto_state = 'External change — auto-save paused'
                elif self.save_document(e, automatic=True): e.auto_state = 'Saved'
                else: e.auto_state = 'Auto-save failed — recovery saved'
            except OSError: e.auto_state = 'Auto-save failed — recovery saved'
        self.update_status()

    def restore_documents(self):
        records = []
        for path in sorted(self.recovery_dir.glob('*.json')):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(data['text'], str) or not isinstance(data['name'], str): raise ValueError('Invalid snapshot')
                if data.get('digest'): bytes.fromhex(data['digest'])
                records.append((path, data))
            except (OSError, ValueError, KeyError, TypeError):
                self.status.showMessage('Unreadable recovery snapshot retained: ' + path.name, 10000)
        if not records: return
        dialog = QDialog(self); dialog.setWindowTitle('Document Recovery'); dialog.resize(580, 360)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('Recovery snapshots are available. Select documents to restore.'))
        scroll = QScrollArea(); scroll.setWidgetResizable(True); content = QWidget(); rows = QVBoxLayout(content)
        boxes = []
        for path, data in records:
            box = QCheckBox(data['name'] + (' — ' + data['path'] if data.get('path') else ' — Untitled'))
            box.setChecked(True); rows.addWidget(box); boxes.append(box)
        rows.addStretch(); scroll.setWidget(content); layout.addWidget(scroll)
        buttons = QDialogButtonBox(); restore = buttons.addButton('Restore Selected', QDialogButtonBox.ButtonRole.AcceptRole)
        discard = buttons.addButton('Discard All', QDialogButtonBox.ButtonRole.DestructiveRole)
        later = buttons.addButton('Later', QDialogButtonBox.ButtonRole.RejectRole)
        restore.clicked.connect(dialog.accept); later.clicked.connect(dialog.reject)
        def discard_all():
            if QMessageBox.question(dialog, 'Discard recovery', 'Permanently discard all listed snapshots?') == QMessageBox.StandardButton.Yes:
                for path, _ in records:
                    try: path.unlink(missing_ok=True)
                    except OSError as exc: self.status.showMessage(str(exc), 8000)
                dialog.reject()
        discard.clicked.connect(discard_all); layout.addWidget(buttons)
        if not dialog.exec(): return
        for (path, data), box in zip(records, boxes):
            if not box.isChecked(): continue
            e = self.tabs.currentWidget()
            if e.path is not None or e.toPlainText() or e.document().isModified():
                self.new_tab(); e = self.tabs.currentWidget()
            e.recovery_id = path.stem
            original = Path(data['path']) if data.get('path') else None
            # Restore as an untitled copy if disk content differs or cannot be read.
            digest = bytes.fromhex(data['digest']) if data.get('digest') else None
            try: safe = original is not None and digest is not None and self.fingerprint(original) == digest and self.find_path(original) is None
            except OSError: safe = False
            e.path = original if safe else None
            e.disk_hash = e.seen_hash = digest if safe else None
            e.bom = bool(data.get('bom')); e.newline = '\r\n' if data.get('newline') == '\r\n' else '\n'
            e.setProperty('filename', data['name'] if safe or original is None else 'Recovered-' + data['name'])
            e.loading = True
            try: e.setPlainText(data['text'])
            finally: e.loading = False
            cursor = e.textCursor(); cursor.setPosition(max(0, min(int(data.get('cursor', 0)), e.document().characterCount()-1))); e.setTextCursor(cursor)
            e.document().setModified(True); e.auto_state = 'Recovery restored'; self.update_tab(e)
            # Do not auto-write restored content until the user edits or manually saves.

    def show_terminal(self,index):
        self.terminals.show(); self.terminals.setCurrentIndex(index)
        if index==1:
            self.terminal_panel.ensure(); self.terminal_panel.sessions.currentWidget().setFocus()

    def set_terminal_size(self,size):
        self.terminal_size=max(8,min(40,int(size))); self.settings.setValue('terminal/size',self.terminal_size); self.settings.sync()
        for session in self.terminal_panel.all_sessions(): session.restyle()

    def terminal_settings(self):
        from PySide6.QtWidgets import QColorDialog, QComboBox
        dialog=QDialog(self); dialog.setWindowTitle('Terminal Settings'); layout=QFormLayout(dialog)
        size=QSpinBox(); size.setRange(8,40); size.setValue(self.terminal_size); layout.addRow('Font size (pt)',size)
        color=QLineEdit(self.terminal_color); color.setPlaceholderText('Empty = application theme'); layout.addRow('Default text color',color)
        shape=QComboBox(); shape.addItems(['Vertical bar','Block','Underline']); shape.setCurrentText(self.terminal_cursor_shape); layout.addRow('Cursor shape',shape)
        blink=QCheckBox(); blink.setChecked(self.terminal_cursor_blink); layout.addRow('Blink cursor',blink)
        layout.addRow('Cursor color',QLabel('Follows terminal text color'))
        choose=QPushButton('Choose color'); layout.addRow(choose)
        def pick():
            value=QColorDialog.getColor(QColor(color.text() or self.colors['fg']),dialog)
            if value.isValid(): color.setText(value.name())
        choose.clicked.connect(pick)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel); layout.addRow(buttons)
        def accept():
            value=color.text().strip()
            if value and not QColor(value).isValid(): QMessageBox.warning(dialog,'Invalid color','Enter a valid color or leave empty.'); return
            self.terminal_cursor_shape=shape.currentText(); self.terminal_cursor_blink=blink.isChecked()
            self.settings.setValue('terminal/cursorShape',self.terminal_cursor_shape); self.settings.setValue('terminal/cursorBlink',self.terminal_cursor_blink)
            self.terminal_color=value; self.settings.setValue('terminal/color',value); self.set_terminal_size(size.value()); dialog.accept()
        buttons.accepted.connect(accept); buttons.rejected.connect(dialog.reject); dialog.exec()

    def toggle_maximize(self):
        if self.isMaximized() or self.isFullScreen(): self.showNormal()
        else: self.showMaximized()

    def toggle_fullscreen(self):
        if self.isFullScreen(): self.showNormal()
        else: self.showFullScreen()

    def about(self):
        QMessageBox.about(self,'About Tux Studio',f"<h2>Tux Studio {VERSION}</h2><p>Development preview</p><p>Tux Studio is a KDE-inspired integrated development environment for writing, exploring and running TUX programs. It brings together a syntax-aware editor, diagnostics, a dedicated TUX console and an integrated system terminal.</p><h3>The TUX language</h3><p>TUX is an independent, interpreted programming language designed for learning, scripting and general-purpose programming. It combines readable syntax, optional type declarations, functions, collections and object-oriented features.</p><p>Its permission-based runtime restricts sensitive operations by default. Full operating system sandboxing is not yet available; run only trusted programs.</p>")

    def system_changed(self,*_):
        self.system_palette=QPalette(self.app.palette())
        if self.mode=='System': self.apply_theme()

    def set_theme(self,mode):
        if mode not in ("System", "Light", "Dark"):
            mode = "System"
        self.mode = mode
        self.settings.setValue("themeMode", mode)
        self.settings.sync()
        self.apply_theme()

    def toggle_theme(self):
        self.set_theme('Light' if self.colors['dark'] else 'Dark')

    def apply_theme(self):
        dark=self.system_palette.color(QPalette.ColorRole.Window).lightness()<128
        if self.mode!='System': dark=self.mode=='Dark'
        hints=self.app.styleHints()
        if self.mode=='System' and hasattr(hints,'colorScheme'):
            scheme=hints.colorScheme()
            if scheme==Qt.ColorScheme.Dark: dark=True
            elif scheme==Qt.ColorScheme.Light: dark=False
        role=getattr(QPalette.ColorRole,'Accent',QPalette.ColorRole.Highlight)
        accent=self.system_palette.color(role)
        if not accent.isValid() or accent.saturation()<35: accent=QColor('#3daee9')
        c=dict(dark=dark,accent=accent.name(),bg='#1e1f22' if dark else '#ffffff',panel='#25272b' if dark else '#f1f2f5',bar='#2b2d31' if dark else '#e9ebf0',fg='#dfe1e5' if dark else '#30323a',muted='#969ba6' if dark else '#626975',border='#41434a' if dark else '#d3d6de',line='#292b32' if dark else '#edf3fa',console='#191a1e' if dark else '#f8f9fb')
        self.colors=c
        self.setStyleSheet(f'''
        QWidget {{background:{c['bg']};color:{c['fg']};font-size:13px;}}
        QWidget#root {{border:1px solid {c['border']};}}
        QWidget#titlebar,QWidget#toolbar,QMenuBar,QStatusBar {{background:{c['bar']};}}
        QLabel {{background:transparent;}} QLabel#brand {{font-weight:600;font-size:15px;}} QLabel#muted {{color:{c['muted']};}}
        QToolButton {{border:0;border-radius:5px;padding:5px;background:transparent;}}
        QToolButton:hover,QMenuBar::item:selected {{background:{c['border']};}}
        QWidget#themeSelector {{background:{c['bg']};border:1px solid {c['border']};border-radius:7px;}}
        QToolButton#themeSegment {{padding:0;border-radius:4px;}}
        QToolButton#themeSegment:checked {{background:{c['border']};border:1px solid {c['accent']};}}
        QToolButton#themeSegment:focus {{border:1px solid {c['accent']};}}
        QToolButton#closeWindow:hover {{background:#c74747;color:white;}}
        QToolButton:disabled,QMenu::item:disabled {{color:{c['muted']};}}
        QMenuBar::item {{padding:6px 11px;background:transparent;}}
        QMenu {{background:{c['bar']};border:1px solid {c['border']};padding:5px;}}
        QMenu::item {{padding:7px 28px 7px 12px;}} QMenu::item:selected {{background:{c['border']};}}
        QTabWidget::pane {{border:0;}} QTabBar::tab {{background:{c['bar']};padding:10px 15px;border-bottom:3px solid transparent;}}
        QTabBar::tab:selected {{background:{c['bg']};border-bottom:3px solid {c['accent']};}}
        QTabBar::tab:hover {{background:{c['panel']};}}
        QSplitter::handle {{background:{c['border']};}} QSplitter::handle:hover {{background:{c['accent']};}}
        QPlainTextEdit {{border:0;selection-background-color:{c['accent']};}}
        QPlainTextEdit#console {{background:{c['console']};padding:12px;}}
        QStatusBar::item {{border:0;}} QStatusBar QLabel {{padding:0 8px;color:{c['muted']};}}
        QLineEdit,QComboBox,QTreeView,QListView {{background:{c['bg']};color:{c['fg']};border:1px solid {c['border']};selection-background-color:{c['accent']};}}
        QPushButton {{background:{c['bar']};border:1px solid {c['border']};border-radius:4px;padding:6px 14px;}}
        QPushButton:hover {{border-color:{c['accent']};}}
        QScrollBar:vertical {{background:{c['panel']};width:11px;}} QScrollBar:horizontal {{background:{c['panel']};height:11px;}}
        QScrollBar::handle {{background:{c['border']};border-radius:4px;min-height:25px;min-width:25px;}}
        QScrollBar::add-line,QScrollBar::sub-line {{width:0;height:0;}}
        ''')
        active = 'Dark' if dark else 'Light'
        for mode, button in self.theme_buttons.items():
            button.setChecked(mode == active)
            color = ('#e6c36a' if dark else '#946a16') if mode == 'Light' and mode == active else c['fg'] if mode == active else c['muted']
            button.setIcon(theme_icon(mode, color))
            button.setToolTip(mode + ' theme (active' + (', following system' if self.mode == 'System' else '') + ')' if mode == active else 'Switch to ' + mode.lower() + ' theme')
        for i in range(self.tabs.count()):
            e=self.tabs.widget(i); e.colors=c; e.set_zoom_size(self.zoom_size); e.highlight(); e.language.highlighter.rehighlight()
        for session in self.terminal_panel.all_sessions(): session.restyle()


def main():
    app=QApplication(sys.argv)
    app.setApplicationName('Tux Studio'); app.setApplicationVersion(VERSION)
    try: window=Studio(app)
    except (OSError, RuntimeError) as exc:
        QMessageBox.critical(None, "Tux Studio startup failed", str(exc)); return 1
    window.show()
    if len(app.arguments()) > 1:
        window.open_paths(app.arguments()[1:])
    return app.exec()


if __name__=='__main__':
    sys.exit(main())
