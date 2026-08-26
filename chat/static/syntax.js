(()=>{
const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const aliases={js:'javascript',jsx:'javascript',ts:'typescript',tsx:'typescript',py:'python',rb:'ruby',sh:'shell',bash:'shell',zsh:'shell',yml:'yaml',cs:'csharp','c#':'csharp',cpp:'cpp','c++':'cpp',htm:'html',svg:'html'};
const labels={javascript:'JavaScript',typescript:'TypeScript',python:'Python',ruby:'Ruby',shell:'Shell',yaml:'YAML',csharp:'C#',cpp:'C++',c:'C',java:'Java',go:'Go',rust:'Rust',php:'PHP',html:'HTML',css:'CSS',json:'JSON',sql:'SQL',xml:'XML',markdown:'Markdown',md:'Markdown'};
const words={
  javascript:'async await break case catch class const continue debugger default delete do else export extends finally for from function get if import in instanceof let new of return set static super switch throw try typeof var void while with yield interface implements private protected public readonly type namespace declare abstract as satisfies',
  typescript:'async await break case catch class const continue default delete do else enum export extends finally for from function get if import in instanceof interface keyof let namespace new of private protected public readonly return set static super switch throw try type typeof var void while yield abstract as declare implements satisfies',
  python:'and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield match case',
  csharp:'abstract as base bool break byte case catch char checked class const continue decimal default delegate do double else enum event explicit extern false finally fixed float for foreach goto if implicit in int interface internal is lock long namespace new null object operator out override params private protected public readonly record ref return sbyte sealed short sizeof stackalloc static string struct switch this throw true try typeof uint ulong unchecked unsafe ushort using virtual void volatile while async await',
  java:'abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally float for goto if implements import instanceof int interface long native new null package private protected public return short static strictfp super switch synchronized this throw throws transient true try void volatile while false',
  c:'auto break case char const continue default do double else enum extern float for goto if inline int long register restrict return short signed sizeof static struct switch typedef union unsigned void volatile while',
  cpp:'alignas alignof and asm auto bitand bool break case catch char class const constexpr continue default delete do double else enum explicit export extern false float for friend if inline int long mutable namespace new noexcept nullptr operator private protected public register reinterpret_cast return short signed sizeof static struct switch template this throw true try typedef typeid typename union unsigned using virtual void volatile while',
  go:'break default func interface select case defer go map struct chan else goto package switch const fallthrough if range type continue for import return var',
  rust:'as async await break const continue crate dyn else enum extern false fn for if impl in let loop match mod move mut pub ref return self Self static struct super trait true type unsafe use where while',
  ruby:'alias and begin break case class def defined do else elsif end ensure false for if in module next nil not or redo rescue retry return self super then true undef unless until when while yield',
  php:'abstract and array as break callable case catch class clone const continue declare default die do echo else elseif empty enddeclare endfor endforeach endif endswitch endwhile eval exit extends final finally fn for foreach function global goto if implements include include_once instanceof insteadof interface isset list match namespace new or print private protected public readonly require require_once return static switch throw trait try unset use var while xor yield',
  sql:'add all alter and any as asc backup between by case check column constraint create database default delete desc distinct drop exec exists foreign from full group having in index inner insert into is join key left like limit not null on or order outer primary procedure right rownum select set table top truncate union unique update values view where with',
  shell:'case do done elif else esac export fi for function if in local readonly return set shift then time trap unset until while'
};
function normalize(value=''){const key=String(value).trim().toLowerCase();return aliases[key]||key}
function detect(code='',hint=''){
  const explicit=normalize(hint);if(explicit)return explicit;
  const text=String(code).trim();
  if(/^<!doctype html|<html\b|<\/?[a-z][\s\S]*>/i.test(text))return'html';
  if(/^\s*[\[{][\s\S]*[\]}]\s*$/.test(text)){try{JSON.parse(text);return'json'}catch{}}
  if(/^#!.*\b(?:ba|z|fi)?sh\b/m.test(text)||/\b(?:echo|printf|chmod|sudo|apt|docker)\s+/.test(text))return'shell';
  if(/\b(?:def|from|import)\s+[A-Za-z_]|\bself\b|:\s*(?:#.*)?$/m.test(text))return'python';
  if(/\busing\s+System\b|\bnamespace\s+[\w.]+|\bpublic\s+(?:sealed\s+)?class\b/.test(text))return'csharp';
  if(/\b(?:const|let|var|function)\s+[A-Za-z_$]|=>|console\./.test(text))return'javascript';
  if(/\b(?:SELECT|INSERT|UPDATE|CREATE TABLE|FROM|WHERE)\b/i.test(text))return'sql';
  if(/^[.#]?[\w-]+(?:\s+[.#]?[\w-]+)*\s*\{[\s\S]*:[^;]+;/m.test(text))return'css';
  if(/^\s*[\w.-]+:\s+.+$/m.test(text))return'yaml';
  return'text';
}
function tokenPattern(language){
  const hashComment=['python','ruby','shell','yaml'].includes(language)?'#[^\\n]*':null;
  const sqlComment=language==='sql'?'--[^\\n]*':null;
  const slashComment=['javascript','typescript','csharp','java','c','cpp','go','rust','php','css'].includes(language)?'\\/\\*[\\s\\S]*?\\*\\/|\\/\\/[^\\n]*':null;
  const comments=[hashComment,sqlComment,slashComment].filter(Boolean).join('|');
  const strings='`(?:\\\\[\\s\\S]|[^`])*`|"(?:\\\\.|[^"\\\\])*"|\'(?:\\\\.|[^\'\\\\])*\'';
  const numbers='\\b(?:0x[\\da-f]+|\\d+(?:\\.\\d+)?(?:e[+-]?\\d+)?)\\b';
  const identifiers='\\b[A-Za-z_$][\\w$]*(?=\\s*\\()';
  return new RegExp([comments,strings,numbers,identifiers,'\\b[A-Za-z_$][\\w$]*\\b'].filter(Boolean).map(value=>`(?:${value})`).join('|'),'gim');
}
function classify(token,language,source='',end=0){
  const lower=token.toLowerCase();
  if(/^\/\*|^\/\/|^#|^--/.test(token))return'comment';
  if(/^[`"']/.test(token))return'string';
  if(/^(?:0x[\da-f]+|\d)/i.test(token))return'number';
  if(new Set((words[language]||'').toLowerCase().split(' ')).has(lower))return'keyword';
  if(/^(true|false|null|none|undefined|nil)$/i.test(token))return'literal';
  if(/^[A-Z][A-Za-z0-9_]*$/.test(token))return'type';
  if(/^\s*\(/.test(source.slice(end)))return'function';
  return'plain';
}
function highlightMarkup(code){
  let output='',last=0;const pattern=/<!--[\s\S]*?-->|<\/?[A-Za-z][^>]*>/g;let match;
  while((match=pattern.exec(code))){output+=esc(code.slice(last,match.index));const token=match[0];if(token.startsWith('<!--'))output+=`<span class="syn-comment">${esc(token)}</span>`;else output+=esc(token).replace(/^(&lt;\/?)([\w:-]+)/,(_,open,tag)=>`${open}<span class="syn-tag">${tag}</span>`).replace(/([\w:-]+)(=)(?=&quot;|&#39;)/g,'<span class="syn-attr">$1</span>$2').replace(/(&quot;[\s\S]*?&quot;|&#39;[\s\S]*?&#39;)/g,'<span class="syn-string">$1</span>');last=pattern.lastIndex}return output+esc(code.slice(last));
}
function highlight(code='',hint=''){
  const language=detect(code,hint);if(language==='html'||language==='xml')return highlightMarkup(String(code));
  const pattern=tokenPattern(language),source=String(code);let output='',last=0,match;
  while((match=pattern.exec(source))){output+=esc(source.slice(last,match.index));output+=`<span class="syn-${classify(match[0],language,source,pattern.lastIndex)}">${esc(match[0])}</span>`;last=pattern.lastIndex}
  return output+esc(source.slice(last));
}
window.AperynSyntax={detect,highlight,label:value=>labels[normalize(value)]||labels[value]||String(value||'Code')};
})();
