// DAG skip-expression tokenizer / parser / evaluator.
//
// Rust port of packages/temper-placer/src/temper_placer/pipeline/dag_expr.py.
// The pinned behavioural oracle is
// packages/temper-placer/tests/pipeline/_dag_expr_py_oracle.py; the
// differential lives in tests/pipeline/test_dag_expr_rust_differential.py.
//
// Grammar (unchanged from the Python):
//   expr       = or_expr
//   or_expr    = and_expr ("or" and_expr)*
//   and_expr   = not_expr ("and" not_expr)*
//   not_expr   = "not" not_expr | comparison
//   comparison = atom (("==" | "!=" | "<" | ">" | "<=" | ">=") atom)?
//   atom       = "true" | "false" | "null" | NUMBER | STRING | accessor
//   accessor   = IDENT "." IDENT
//
// ---------------------------------------------------------------------------
// Design decision: reuse Python's own regex source strings via the `regex`
// crate, rather than hand-rolling character classes.
// ---------------------------------------------------------------------------
// The Python tokenizer is a 19-entry ordered `_TOKEN_SPEC` of compiled `re`
// patterns driven by `pattern.match(source, pos)`. Hand-rolling those matchers
// in Rust would silently diverge in at least four places that this grammar
// really can reach:
//
//   1. `\d` in a Python `str` pattern is Unicode-aware (category Nd), so
//      `٥` (U+0665) tokenizes as NUMBER and `int("٥")` is 5. A naive
//      `c.is_ascii_digit()` would reject it; `char::is_numeric()` would
//      over-accept (`½`, `Ⅴ` are Nl/No, which `\d` does NOT match).
//   2. `\b` in the keyword patterns (`not\b`, `and\b`, ...) is Unicode-aware
//      in both engines, so `notx` and `noté` must both fall through to IDENT.
//   3. `.` inside the string pattern's `(?:\\.[^'\\]*)*` does NOT match a
//      newline in either engine, so `'a\<LF>b'` fails to tokenize as a STRING
//      and ends up an "Unexpected character" error on the opening quote.
//   4. Leftmost-first alternation with greedy quantifiers in
//      `(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?`.
//
// `regex::Regex::captures_at(h, start)` has exactly `pattern.match(h, pos)`'s
// semantics -- it anchors the *start* of the match at `start` when we assert
// `m.start() == start`, and its lookaround (`\b`) still sees the text before
// `start`, which a `&h[start..]` slice would not. So the patterns below are
// character-for-character the Python ones.
//
// Byte offsets vs character offsets: Python reports `pos` as a CHARACTER
// index (`f"... at position {pos}"`, `source[pos]`). `regex` works in bytes.
// `Tokenizer` therefore advances `bpos` and `cpos` in lockstep and every
// public position is the character one.

use std::sync::OnceLock;

use regex::Regex;

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/// Which Python exception class the shim must raise for this error.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrKind {
    /// -> `temper_placer.pipeline.dag_types.DAGExprSyntaxError`
    Syntax,
    /// -> `temper_placer.pipeline.dag_types.DAGExprError`
    Runtime,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExprError {
    pub kind: ErrKind,
    pub message: String,
}

impl ExprError {
    fn syntax(message: impl Into<String>) -> Self {
        Self { kind: ErrKind::Syntax, message: message.into() }
    }
    fn runtime(message: impl Into<String>) -> Self {
        Self { kind: ErrKind::Runtime, message: message.into() }
    }
}

// ---------------------------------------------------------------------------
// Python `str.strip()`
// ---------------------------------------------------------------------------

/// Exactly the character set for which CPython's `str.isspace()` is true.
///
/// `str.strip()` (used by `parse_skip_expr`) strips this set, which is NOT the
/// same as Rust's `char::is_whitespace()` (the Unicode `White_Space`
/// property). The two differ on U+001C..U+001F (INFORMATION SEPARATOR FOUR..
/// ONE): CPython's `isspace()` is true -- they carry bidirectional class B/S
/// -- while `White_Space` is false. Stripping the wrong set would shift every
/// reported error `position` by the number of mis-stripped leading chars, so
/// this is load-bearing, not cosmetic.
pub fn is_python_space(c: char) -> bool {
    matches!(
        c,
        '\u{09}'..='\u{0d}'      // TAB LF VT FF CR
            | '\u{1c}'..='\u{1f}' // INFORMATION SEPARATOR FOUR..ONE
            | '\u{20}'            // SPACE
            | '\u{85}'            // NEXT LINE
            | '\u{a0}'            // NO-BREAK SPACE
            | '\u{1680}'          // OGHAM SPACE MARK
            | '\u{2000}'..='\u{200a}'
            | '\u{2028}'          // LINE SEPARATOR
            | '\u{2029}'          // PARAGRAPH SEPARATOR
            | '\u{202f}'          // NARROW NO-BREAK SPACE
            | '\u{205f}'          // MEDIUM MATHEMATICAL SPACE
            | '\u{3000}' // IDEOGRAPHIC SPACE
    )
}

/// `str.strip()` with no argument, matching CPython.
pub fn python_strip(s: &str) -> &str {
    s.trim_matches(is_python_space)
}

// ---------------------------------------------------------------------------
// Tokens
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TokKind {
    Str,
    Num,
    Null,
    True,
    False,
    And,
    Or,
    Not,
    Eq,
    Neq,
    Lte,
    Gte,
    Lt,
    Gt,
    LParen,
    RParen,
    Dot,
    Ident,
    Eof,
}

impl TokKind {
    /// The literal name Python puts in its error strings (the `_TOKEN_SPEC`
    /// keys), e.g. `Expected RPAREN, got EOF ('') at position 4`.
    pub fn name(self) -> &'static str {
        match self {
            TokKind::Str => "STRING",
            TokKind::Num => "NUMBER",
            TokKind::Null => "NULL",
            TokKind::True => "TRUE",
            TokKind::False => "FALSE",
            TokKind::And => "AND",
            TokKind::Or => "OR",
            TokKind::Not => "NOT",
            TokKind::Eq => "EQ",
            TokKind::Neq => "NEQ",
            TokKind::Lte => "LTE",
            TokKind::Gte => "GTE",
            TokKind::Lt => "LT",
            TokKind::Gt => "GT",
            TokKind::LParen => "LPAREN",
            TokKind::RParen => "RPAREN",
            TokKind::Dot => "DOT",
            TokKind::Ident => "IDENT",
            TokKind::Eof => "EOF",
        }
    }
}

/// A token.
///
/// `text` is `Option` solely to reproduce one CPython wart faithfully. The
/// tokenizer stores `m.group(1) or m.group(2)` for STRING tokens. For the
/// *single*-quoted branch group(2) is `None`, so an empty single-quoted string
/// `''` yields group(1) == `""`, which is falsy, and the `or` therefore
/// evaluates to `None`. The token value of `''` is thus Python `None`, not
/// `""` -- and `'' == ""` evaluates to **False**, because it is really
/// `None == ""`. `""` is unaffected (group(1) is None, `None or ""` is `""`).
/// See `test_empty_single_quote_is_none_wart`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Token {
    pub kind: TokKind,
    pub text: Option<String>,
    pub pos: usize,
}

impl Token {
    /// How Python's f-strings render `tok[1]` -- `None` becomes `None`.
    fn display_text(&self) -> &str {
        self.text.as_deref().unwrap_or("None")
    }
}

// ---------------------------------------------------------------------------
// Compiled patterns -- character-for-character Python's `_TOKEN_SPEC`.
// ---------------------------------------------------------------------------

struct Patterns {
    string: Regex,
    number: Regex,
    null: Regex,
    r#true: Regex,
    r#false: Regex,
    and: Regex,
    or: Regex,
    not: Regex,
    ident: Regex,
    skip: Regex,
}

static PATTERNS: OnceLock<Option<Patterns>> = OnceLock::new();

fn patterns() -> Result<&'static Patterns, ExprError> {
    PATTERNS
        .get_or_init(|| {
            Some(Patterns {
                string: Regex::new(r#"'([^'\\]*(?:\\.[^'\\]*)*)'|"([^"\\]*(?:\\.[^"\\]*)*)""#)
                    .ok()?,
                number: Regex::new(r"(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?").ok()?,
                null: Regex::new(r"null\b").ok()?,
                r#true: Regex::new(r"true\b").ok()?,
                r#false: Regex::new(r"false\b").ok()?,
                and: Regex::new(r"and\b").ok()?,
                or: Regex::new(r"or\b").ok()?,
                not: Regex::new(r"not\b").ok()?,
                ident: Regex::new(r"[a-zA-Z_][a-zA-Z0-9_]*").ok()?,
                skip: Regex::new(r"[ \t]+").ok()?,
            })
        })
        .as_ref()
        .ok_or_else(|| ExprError::runtime("internal error: dag_expr pattern compilation failed"))
}

// ---------------------------------------------------------------------------
// Tokenizer
// ---------------------------------------------------------------------------

/// Tokenize `source`, mirroring `_tokenize`.
///
/// Positions in the returned tokens and in any error message are CHARACTER
/// indices into `source`, matching CPython.
pub fn tokenize(source: &str) -> Result<Vec<Token>, ExprError> {
    let pats = patterns()?;
    let mut tokens: Vec<Token> = Vec::new();
    let mut bpos = 0usize; // byte offset
    let mut cpos = 0usize; // character offset

    while bpos < source.len() {
        // `_TOKEN_SPEC` order is load-bearing: first pattern that matches
        // wins. NUMBER precedes DOT so `.5` is a NUMBER, not a DOT; the
        // `\b`-terminated keywords precede IDENT so `not` is NOT and `notx`
        // is IDENT.
        let matched = match_string(pats, source, bpos)
            .or_else(|| match_simple(&pats.number, TokKind::Num, source, bpos))
            .or_else(|| match_simple(&pats.null, TokKind::Null, source, bpos))
            .or_else(|| match_simple(&pats.r#true, TokKind::True, source, bpos))
            .or_else(|| match_simple(&pats.r#false, TokKind::False, source, bpos))
            .or_else(|| match_simple(&pats.and, TokKind::And, source, bpos))
            .or_else(|| match_simple(&pats.or, TokKind::Or, source, bpos))
            .or_else(|| match_simple(&pats.not, TokKind::Not, source, bpos))
            .or_else(|| match_literal("==", TokKind::Eq, source, bpos))
            .or_else(|| match_literal("!=", TokKind::Neq, source, bpos))
            .or_else(|| match_literal("<=", TokKind::Lte, source, bpos))
            .or_else(|| match_literal(">=", TokKind::Gte, source, bpos))
            .or_else(|| match_literal("<", TokKind::Lt, source, bpos))
            .or_else(|| match_literal(">", TokKind::Gt, source, bpos))
            .or_else(|| match_literal("(", TokKind::LParen, source, bpos))
            .or_else(|| match_literal(")", TokKind::RParen, source, bpos))
            .or_else(|| match_literal(".", TokKind::Dot, source, bpos))
            .or_else(|| match_simple(&pats.ident, TokKind::Ident, source, bpos))
            .or_else(|| match_skip(&pats.skip, source, bpos));

        match matched {
            Some(Matched { kind, text, bend }) => {
                let consumed = char_len(source, bpos, bend);
                if let Some(kind) = kind {
                    tokens.push(Token { kind, text, pos: cpos });
                }
                bpos = bend;
                cpos += consumed;
            }
            None => {
                // MISMATCH: `.` matched a single character.
                let ch = source[bpos..].chars().next().unwrap_or('\u{fffd}');
                return Err(ExprError::syntax(format!(
                    "Unexpected character '{ch}' at position {cpos}"
                )));
            }
        }
    }

    tokens.push(Token { kind: TokKind::Eof, text: Some(String::new()), pos: cpos });
    Ok(tokens)
}

struct Matched {
    /// `None` for SKIP, which consumes input without emitting a token.
    kind: Option<TokKind>,
    text: Option<String>,
    bend: usize,
}

fn char_len(source: &str, from: usize, to: usize) -> usize {
    source.get(from..to).map_or(0, |s| s.chars().count())
}

fn match_simple(re: &Regex, kind: TokKind, source: &str, bpos: usize) -> Option<Matched> {
    let m = re.find_at(source, bpos)?;
    if m.start() != bpos {
        return None;
    }
    Some(Matched { kind: Some(kind), text: Some(m.as_str().to_string()), bend: m.end() })
}

fn match_literal(lit: &str, kind: TokKind, source: &str, bpos: usize) -> Option<Matched> {
    if source.get(bpos..)?.starts_with(lit) {
        Some(Matched {
            kind: Some(kind),
            text: Some(lit.to_string()),
            bend: bpos + lit.len(),
        })
    } else {
        None
    }
}

fn match_skip(re: &Regex, source: &str, bpos: usize) -> Option<Matched> {
    let m = re.find_at(source, bpos)?;
    if m.start() != bpos {
        return None;
    }
    Some(Matched { kind: None, text: None, bend: m.end() })
}

/// STRING, reproducing `tokens.append((kind, m.group(1) or m.group(2), pos))`.
fn match_string(pats: &Patterns, source: &str, bpos: usize) -> Option<Matched> {
    let caps = pats.string.captures_at(source, bpos)?;
    let whole = caps.get(0)?;
    if whole.start() != bpos {
        return None;
    }
    // Python's `or`: group(1) wins only when it is truthy (non-empty).
    let g1 = caps.get(1).map(|m| m.as_str());
    let g2 = caps.get(2).map(|m| m.as_str());
    let text = match g1 {
        Some(s) if !s.is_empty() => Some(s.to_string()),
        // group(1) matched but is empty (`''`) -> falls through to group(2),
        // which is None for the single-quoted branch. Hence Python `None`.
        Some(_) => g2.map(str::to_string),
        None => g2.map(str::to_string),
    };
    Some(Matched { kind: Some(TokKind::Str), text, bend: whole.end() })
}

// ---------------------------------------------------------------------------
// AST
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CmpOp {
    Eq,
    NotEq,
    Lt,
    Gt,
    LtE,
    GtE,
}

impl CmpOp {
    /// The Python `ast` class name, used when materialising the compatibility
    /// `ast.Expression` tree on the Python side.
    pub fn ast_name(self) -> &'static str {
        match self {
            CmpOp::Eq => "Eq",
            CmpOp::NotEq => "NotEq",
            CmpOp::Lt => "Lt",
            CmpOp::Gt => "Gt",
            CmpOp::LtE => "LtE",
            CmpOp::GtE => "GtE",
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum Node {
    /// `true` / `false`
    Bool(bool),
    /// `null`, and the `''` wart (see `Token`).
    None_,
    /// Integer literal, kept as source text: CPython `int()` is arbitrary
    /// precision and Unicode-digit aware, so the value is materialised by
    /// calling Python's own `int()` rather than parsed in Rust.
    Int(String),
    /// Float literal, kept as source text for the same reason (`float()`).
    Float(String),
    Str(String),
    Not(Box<Node>),
    And(Box<Node>, Box<Node>),
    Or(Box<Node>, Box<Node>),
    Cmp { left: Box<Node>, op: CmpOp, right: Box<Node> },
    Accessor { ns: String, field: String },
}

// ---------------------------------------------------------------------------
// Parser
// ---------------------------------------------------------------------------

/// Parser recursion ceiling, counted in PARSER FRAMES (not nesting levels).
///
/// One level of `(` costs four frames here -- `expr` -> `and_expr` ->
/// `comparison` -> `atom` -- so this is roughly `MAX_DEPTH / 4` levels of
/// nesting. Getting that unit wrong is not hypothetical: the first version of
/// this constant was 180 and read as "levels", which made the port reject at
/// nesting depth 60 input that CPython parses without complaint. The
/// differential caught it.
///
/// The Python parser is recursive too, so deep input raises `RecursionError`
/// there; measured on CPython 3.12 with the default `recursionlimit` of 1000,
/// it gives up at nesting depth 199. Rust has no such guard and would
/// overflow the stack -- an abort, not an exception -- so this port needs an
/// explicit limit.
///
/// 1000 frames is ~250 nesting levels: comfortably above CPython's 199, so
/// the Rust side never rejects input the oracle parses, and small enough to
/// stay inside a 2 MiB thread stack in an unoptimised build. (4000 was tried
/// first and aborted the debug test binary with a stack overflow -- the
/// ceiling has to fit the *smallest* stack this code runs on, not the main
/// thread's.)
///
/// This is a stack-safety backstop, NOT a parity claim: the two ceilings
/// differ, and `test_witness_deep_nesting_divergence` pins that explicitly
/// rather than hiding it by shrinking the differential's input range. Raising
/// `sys.setrecursionlimit` far above the default would let CPython parse
/// deeper than this limit allows; that is a documented, witnessed difference.
pub const MAX_DEPTH: usize = 1000;

struct Parser {
    tokens: Vec<Token>,
    pos: usize,
    depth: usize,
}

impl Parser {
    fn new(tokens: Vec<Token>) -> Self {
        Self { tokens, pos: 0, depth: 0 }
    }

    fn peek(&self) -> Result<&Token, ExprError> {
        self.tokens
            .get(self.pos)
            .ok_or_else(|| ExprError::runtime("internal error: token cursor past EOF"))
    }

    fn advance(&mut self) -> Result<Token, ExprError> {
        let tok = self
            .tokens
            .get(self.pos)
            .cloned()
            .ok_or_else(|| ExprError::runtime("internal error: token cursor past EOF"))?;
        self.pos += 1;
        Ok(tok)
    }

    fn expect(&mut self, kind: TokKind) -> Result<Token, ExprError> {
        let tok = self.advance()?;
        if tok.kind != kind {
            return Err(ExprError::syntax(format!(
                "Expected {}, got {} ('{}') at position {}",
                kind.name(),
                tok.kind.name(),
                tok.display_text(),
                tok.pos
            )));
        }
        Ok(tok)
    }

    fn enter(&mut self) -> Result<(), ExprError> {
        self.depth += 1;
        if self.depth > MAX_DEPTH {
            return Err(ExprError::runtime(format!(
                "skip expression exceeds the parser recursion limit of {MAX_DEPTH} frames"
            )));
        }
        Ok(())
    }

    fn leave(&mut self) {
        self.depth -= 1;
    }

    fn parse(&mut self) -> Result<Node, ExprError> {
        let node = self.expr()?;
        self.expect(TokKind::Eof)?;
        Ok(node)
    }

    fn expr(&mut self) -> Result<Node, ExprError> {
        self.enter()?;
        let mut left = self.and_expr()?;
        while self.peek()?.kind == TokKind::Or {
            self.advance()?;
            let right = self.and_expr()?;
            left = Node::Or(Box::new(left), Box::new(right));
        }
        self.leave();
        Ok(left)
    }

    fn and_expr(&mut self) -> Result<Node, ExprError> {
        self.enter()?;
        let mut left = self.not_expr()?;
        while self.peek()?.kind == TokKind::And {
            self.advance()?;
            let right = self.not_expr()?;
            left = Node::And(Box::new(left), Box::new(right));
        }
        self.leave();
        Ok(left)
    }

    fn not_expr(&mut self) -> Result<Node, ExprError> {
        // Counted rather than recursed: a chain of `not` is unbounded in
        // arity but bounded in meaning, and folding it iteratively keeps the
        // Rust stack flat. Depth is still charged so the ceiling above is not
        // silently bypassed.
        let mut nots = 0usize;
        while self.peek()?.kind == TokKind::Not {
            self.advance()?;
            nots += 1;
            self.enter()?;
        }
        let mut node = self.comparison()?;
        for _ in 0..nots {
            node = Node::Not(Box::new(node));
            self.leave();
        }
        Ok(node)
    }

    fn comparison(&mut self) -> Result<Node, ExprError> {
        self.enter()?;
        let left = self.atom()?;
        let op = match self.peek()?.kind {
            TokKind::Eq => Some(CmpOp::Eq),
            TokKind::Neq => Some(CmpOp::NotEq),
            TokKind::Lt => Some(CmpOp::Lt),
            TokKind::Gt => Some(CmpOp::Gt),
            TokKind::Lte => Some(CmpOp::LtE),
            TokKind::Gte => Some(CmpOp::GtE),
            _ => None,
        };
        let out = match op {
            Some(op) => {
                self.advance()?;
                let right = self.atom()?;
                Node::Cmp { left: Box::new(left), op, right: Box::new(right) }
            }
            None => left,
        };
        self.leave();
        Ok(out)
    }

    fn atom(&mut self) -> Result<Node, ExprError> {
        self.enter()?;
        let tok = self.advance()?;
        let node = match tok.kind {
            TokKind::LParen => {
                let node = self.expr()?;
                self.expect(TokKind::RParen)?;
                node
            }
            TokKind::True => Node::Bool(true),
            TokKind::False => Node::Bool(false),
            TokKind::Null => Node::None_,
            TokKind::Num => {
                let text = tok.text.clone().unwrap_or_default();
                // `if "." in text or "e" in text.lower()`
                if text.contains('.') || text.to_lowercase().contains('e') {
                    Node::Float(text)
                } else {
                    Node::Int(text)
                }
            }
            TokKind::Str => match tok.text.clone() {
                // The `''` wart: token value is Python `None`, so the
                // constant is `None`, not the empty string.
                None => Node::None_,
                Some(s) => Node::Str(s),
            },
            TokKind::Ident => {
                let ident = tok.text.clone().unwrap_or_default();
                if self.peek()?.kind == TokKind::Dot {
                    self.advance()?;
                    let field = self.expect(TokKind::Ident)?;
                    Node::Accessor { ns: ident, field: field.text.unwrap_or_default() }
                } else {
                    return Err(ExprError::syntax(format!(
                        "Bare identifier '{ident}' not allowed; \
                         use config.{ident}, state.{ident}, or context.{ident}"
                    )));
                }
            }
            _ => {
                return Err(ExprError::syntax(format!(
                    "Unexpected token {} ('{}') at position {}",
                    tok.kind.name(),
                    tok.display_text(),
                    tok.pos
                )));
            }
        };
        self.leave();
        Ok(node)
    }
}

/// Parse a skip expression, mirroring `parse_skip_expr`.
pub fn parse(source: &str) -> Result<Node, ExprError> {
    let stripped = python_strip(source);
    if stripped.is_empty() {
        return Err(ExprError::syntax("Empty skip expression"));
    }
    let tokens = tokenize(stripped)?;
    Parser::new(tokens).parse()
}

// ---------------------------------------------------------------------------
// pyo3 boundary
// ---------------------------------------------------------------------------
//
// Note on floating point: this module performs NO arithmetic. The only
// float-valued operation in the whole surface is decimal-literal conversion
// (`float("1.5")`), which is delegated to CPython's own `float()` below, and
// every comparison is delegated to CPython's rich-compare protocol. There is
// no reduction, no dot product and no `np.linalg.norm`, so the OpenBLAS
// FMA-contraction hazard (which makes small `np.dot` reductions
// CPU-dependent) has no reach here and parity is unconditional rather than
// platform-conditional. See VERIFICATION.md.

#[cfg(feature = "python")]
pub use python::{DagExprError, DagExprSyntaxError, PySkipExpr, parse_skip_expr_rs};

#[cfg(feature = "python")]
mod python {
    use pyo3::basic::CompareOp;
    use pyo3::create_exception;
    use pyo3::exceptions::{PyAttributeError, PyException};
    use pyo3::prelude::*;
    use pyo3::types::{PyBool, PyString, PyTuple};

    use super::{CmpOp, ErrKind, ExprError, Node};

    create_exception!(
        temper_io_types,
        DagExprSyntaxError,
        PyException,
        "Raised for skip-expression syntax errors; the Python shim re-raises \
         this as temper_placer.pipeline.dag_types.DAGExprSyntaxError."
    );
    create_exception!(
        temper_io_types,
        DagExprError,
        PyException,
        "Raised for skip-expression evaluation errors; the Python shim \
         re-raises this as temper_placer.pipeline.dag_types.DAGExprError."
    );

    fn to_py_err(e: ExprError) -> PyErr {
        match e.kind {
            ErrKind::Syntax => DagExprSyntaxError::new_err(e.message),
            ErrKind::Runtime => DagExprError::new_err(e.message),
        }
    }

    /// A parsed node with its constants already materialised as Python
    /// objects, so evaluation never re-parses a literal.
    enum CNode {
        Const(Py<PyAny>),
        Not(Box<CNode>),
        And(Box<CNode>, Box<CNode>),
        Or(Box<CNode>, Box<CNode>),
        Cmp { left: Box<CNode>, op: CmpOp, right: Box<CNode> },
        Accessor { ns: String, field: String },
    }

    /// Build the constant pool.
    ///
    /// Integer and float literals are converted by calling CPython's own
    /// `int()` / `float()`. That is not laziness: CPython integers are
    /// arbitrary precision (`99999999999999999999` is exact, `i64` is not)
    /// and both builtins accept Unicode decimal digits, which the `\d` in the
    /// NUMBER pattern really does match. Rust-side parsing would diverge on
    /// both counts.
    fn compile(py: Python<'_>, node: &Node) -> PyResult<CNode> {
        Ok(match node {
            Node::Bool(b) => CNode::Const(PyBool::new(py, *b).to_owned().into_any().unbind()),
            Node::None_ => CNode::Const(py.None()),
            Node::Int(text) => {
                let s = PyString::new(py, text);
                CNode::Const(py.get_type::<pyo3::types::PyInt>().call1((s,))?.unbind())
            }
            Node::Float(text) => {
                let s = PyString::new(py, text);
                CNode::Const(py.get_type::<pyo3::types::PyFloat>().call1((s,))?.unbind())
            }
            Node::Str(s) => CNode::Const(PyString::new(py, s).into_any().unbind()),
            Node::Not(inner) => CNode::Not(Box::new(compile(py, inner)?)),
            Node::And(l, r) => {
                CNode::And(Box::new(compile(py, l)?), Box::new(compile(py, r)?))
            }
            Node::Or(l, r) => CNode::Or(Box::new(compile(py, l)?), Box::new(compile(py, r)?)),
            Node::Cmp { left, op, right } => CNode::Cmp {
                left: Box::new(compile(py, left)?),
                op: *op,
                right: Box::new(compile(py, right)?),
            },
            Node::Accessor { ns, field } => {
                CNode::Accessor { ns: ns.clone(), field: field.clone() }
            }
        })
    }

    fn cmp_op(op: CmpOp) -> CompareOp {
        match op {
            CmpOp::Eq => CompareOp::Eq,
            CmpOp::NotEq => CompareOp::Ne,
            CmpOp::Lt => CompareOp::Lt,
            CmpOp::Gt => CompareOp::Gt,
            CmpOp::LtE => CompareOp::Le,
            CmpOp::GtE => CompareOp::Ge,
        }
    }

    /// Resolve `config.x` / `state.x`, reproducing the Python's
    /// `hasattr(...)` followed by `getattr(...)`.
    ///
    /// The DOUBLE lookup is deliberate. The oracle really does evaluate the
    /// attribute twice, which is observable for a `property` with side
    /// effects, and `hasattr` swallows ONLY `AttributeError` -- any other
    /// exception from the property propagates to the caller unchanged rather
    /// than being reported as an unknown field.
    fn resolve_attr(
        obj: &Bound<'_, PyAny>,
        field: &str,
        what: &str,
    ) -> PyResult<Py<PyAny>> {
        match obj.getattr(field) {
            Err(e) if e.is_instance_of::<PyAttributeError>(obj.py()) => Err(
                DagExprError::new_err(format!(
                    "Unknown {what} field '{field}' in skip expression"
                )),
            ),
            Err(e) => Err(e),
            Ok(_) => Ok(obj.getattr(field)?.unbind()),
        }
    }

    fn eval<'py>(
        py: Python<'py>,
        node: &CNode,
        config: &Bound<'py, PyAny>,
        state: &Bound<'py, PyAny>,
        context: &Bound<'py, PyAny>,
    ) -> PyResult<Py<PyAny>> {
        match node {
            CNode::Const(v) => Ok(v.clone_ref(py)),

            // `not _eval(operand)` -> a bool, never the operand.
            CNode::Not(inner) => {
                let v = eval(py, inner, config, state, context)?;
                let truthy = v.bind(py).is_truthy()?;
                Ok(PyBool::new(py, !truthy).to_owned().into_any().unbind())
            }

            // `all(_eval(v) for v in values)` over a GENERATOR: short-circuits
            // on the first falsy operand (so the right operand is not
            // evaluated at all) and yields a bool, not the operand value.
            CNode::And(l, r) => {
                let lv = eval(py, l, config, state, context)?;
                if !lv.bind(py).is_truthy()? {
                    return Ok(PyBool::new(py, false).to_owned().into_any().unbind());
                }
                let rv = eval(py, r, config, state, context)?;
                let t = rv.bind(py).is_truthy()?;
                Ok(PyBool::new(py, t).to_owned().into_any().unbind())
            }

            // `any(...)`, same generator short-circuit.
            CNode::Or(l, r) => {
                let lv = eval(py, l, config, state, context)?;
                if lv.bind(py).is_truthy()? {
                    return Ok(PyBool::new(py, true).to_owned().into_any().unbind());
                }
                let rv = eval(py, r, config, state, context)?;
                let t = rv.bind(py).is_truthy()?;
                Ok(PyBool::new(py, t).to_owned().into_any().unbind())
            }

            // Comparison itself is CPython's rich-compare protocol, so
            // int/float promotion, string ordering, and the TypeError raised
            // by e.g. `None < 1` are all CPython's, byte for byte.
            CNode::Cmp { left, op, right } => {
                let lv = eval(py, left, config, state, context)?;
                let rv = eval(py, right, config, state, context)?;
                let result = lv.bind(py).rich_compare(rv.bind(py), cmp_op(*op))?;
                let ok = result.is_truthy()?;
                Ok(PyBool::new(py, ok).to_owned().into_any().unbind())
            }

            CNode::Accessor { ns, field } => match ns.as_str() {
                "config" => resolve_attr(config, field, "config"),
                "state" => resolve_attr(state, field, "state"),
                "context" => {
                    if !context.contains(field)? {
                        return Err(DagExprError::new_err(format!(
                            "Unknown context key '{field}' in skip expression"
                        )));
                    }
                    Ok(context.get_item(field)?.unbind())
                }
                other => Err(DagExprError::new_err(format!(
                    "Unknown namespace '{other}' in skip expression"
                ))),
            },
        }
    }

    /// Opaque handle to a parsed skip expression.
    ///
    /// Deliberately carries no `__eq__`/`__hash__`/`__repr__` beyond the
    /// defaults: the Python `parse_skip_expr` returns an `ast.Expression`
    /// exactly as before and merely *attaches* one of these, so this type is
    /// not part of the public surface and must not accidentally change how
    /// the `ast.Expression` compares.
    #[pyclass(name = "SkipExpr", module = "temper_io_types", frozen)]
    pub struct PySkipExpr {
        root: CNode,
        source: String,
    }

    fn spec<'py>(py: Python<'py>, node: &CNode) -> PyResult<Bound<'py, PyAny>> {
        // ("const", value) | ("not", x) | ("and"|"or", l, r)
        // | ("cmp", l, op_name, r) | ("accessor", ns, field)
        let t = match node {
            CNode::Const(v) => {
                PyTuple::new(py, [PyString::new(py, "const").into_any(), v.bind(py).clone()])?
            }
            CNode::Not(inner) => PyTuple::new(
                py,
                [PyString::new(py, "not").into_any(), spec(py, inner)?],
            )?,
            CNode::And(l, r) => PyTuple::new(
                py,
                [PyString::new(py, "and").into_any(), spec(py, l)?, spec(py, r)?],
            )?,
            CNode::Or(l, r) => PyTuple::new(
                py,
                [PyString::new(py, "or").into_any(), spec(py, l)?, spec(py, r)?],
            )?,
            CNode::Cmp { left, op, right } => PyTuple::new(
                py,
                [
                    PyString::new(py, "cmp").into_any(),
                    spec(py, left)?,
                    PyString::new(py, op.ast_name()).into_any(),
                    spec(py, right)?,
                ],
            )?,
            CNode::Accessor { ns, field } => PyTuple::new(
                py,
                [
                    PyString::new(py, "accessor").into_any(),
                    PyString::new(py, ns).into_any(),
                    PyString::new(py, field).into_any(),
                ],
            )?,
        };
        Ok(t.into_any())
    }

    #[pymethods]
    impl PySkipExpr {
        /// The stripped source this was parsed from.
        #[getter]
        fn source(&self) -> &str {
            &self.source
        }

        /// Nested-tuple description of the tree, used by the Python shim to
        /// materialise the compatibility `ast.Expression`.
        fn to_spec<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
            spec(py, &self.root)
        }

        /// Evaluate against live objects. Returns a `bool`, matching
        /// `evaluate_skip_expr`'s closing `bool(...)`.
        fn evaluate(
            &self,
            py: Python<'_>,
            config: &Bound<'_, PyAny>,
            state: &Bound<'_, PyAny>,
            context: &Bound<'_, PyAny>,
        ) -> PyResult<bool> {
            let v = eval(py, &self.root, config, state, context)?;
            v.bind(py).is_truthy()
        }

        /// Support `copy.deepcopy` and `pickle` by round-tripping the source.
        ///
        /// A `#[pyclass]` is unpicklable by default, and this object gets
        /// attached to an `ast.Expression` that callers may well copy. #724
        /// in this program shipped a green 941-assertion differential while
        /// `pickle`/`deepcopy` were quietly broken because nothing exercised
        /// them, so this is covered explicitly by
        /// `test_skip_expr_pickle_and_deepcopy_roundtrip`.
        fn __reduce__(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
            let f = py.import("temper_io_types")?.getattr("parse_skip_expr_rs")?;
            let args = PyTuple::new(py, [PyString::new(py, &self.source)])?;
            Ok(PyTuple::new(py, [f.into_any(), args.into_any()])?.into_any().unbind())
        }
    }

    /// Tokenize + parse `source`.
    #[pyfunction]
    pub fn parse_skip_expr_rs(py: Python<'_>, source: &str) -> PyResult<PySkipExpr> {
        let node = super::parse(source).map_err(to_py_err)?;
        Ok(PySkipExpr {
            root: compile(py, &node)?,
            source: super::python_strip(source).to_string(),
        })
    }
}

// ---------------------------------------------------------------------------
// Pure-Rust unit tests (R1f: these were written before the port compiled)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn parse_ok(src: &str) -> Node {
        match parse(src) {
            Ok(n) => n,
            Err(e) => panic!("expected parse to succeed for {src:?}, got {e:?}"),
        }
    }

    fn parse_err(src: &str) -> ExprError {
        match parse(src) {
            Ok(n) => panic!("expected parse to fail for {src:?}, got {n:?}"),
            Err(e) => e,
        }
    }

    #[test]
    fn empty_source_is_syntax_error() {
        let e = parse_err("   ");
        assert_eq!(e.kind, ErrKind::Syntax);
        assert_eq!(e.message, "Empty skip expression");
    }

    #[test]
    fn bare_identifier_message_matches_python() {
        let e = parse_err("foo");
        assert_eq!(
            e.message,
            "Bare identifier 'foo' not allowed; use config.foo, state.foo, or context.foo"
        );
    }

    #[test]
    fn keyword_boundary_is_respected() {
        // `not` is NOT; `notx` is a bare IDENT, so it reports as such.
        assert!(matches!(parse_ok("not true"), Node::Not(_)));
        assert!(parse_err("notx").message.starts_with("Bare identifier 'notx'"));
    }

    #[test]
    fn empty_single_quote_is_none_wart() {
        // `''` -> group(1) == "" is falsy -> `or group(2)` -> None.
        assert_eq!(parse_ok("''"), Node::None_);
        // `""` -> group(1) is None -> `None or ""` -> "".
        assert_eq!(parse_ok("\"\""), Node::Str(String::new()));
    }

    #[test]
    fn number_classification_matches_python() {
        assert_eq!(parse_ok("1"), Node::Int("1".into()));
        assert_eq!(parse_ok("1."), Node::Float("1.".into()));
        assert_eq!(parse_ok(".5"), Node::Float(".5".into()));
        assert_eq!(parse_ok("1e3"), Node::Float("1e3".into()));
        assert_eq!(parse_ok("1E3"), Node::Float("1E3".into()));
    }

    #[test]
    fn error_positions_are_character_indices() {
        // A 3-byte character before the offending one must not shift `pos`:
        // the `@` is the 17th CHARACTER (index 16) but the 19th byte. Value
        // confirmed against CPython, which is the authority here.
        let e = parse_err("config.a == '\u{4e2d}' @");
        assert_eq!(e.message, "Unexpected character '@' at position 16");
    }

    #[test]
    fn python_strip_covers_information_separators() {
        // U+001C is `str.isspace()` in CPython but not `char::is_whitespace()`.
        assert_eq!(python_strip("\u{1c}true\u{1c}"), "true");
        assert!(is_python_space('\u{1f}'));
    }

    #[test]
    fn newline_escape_does_not_close_a_string() {
        // `\\.` cannot match a newline, so the STRING pattern fails and the
        // opening quote becomes the "Unexpected character".
        let e = parse_err("'a\\\nb'");
        assert!(e.message.starts_with("Unexpected character '''"), "{}", e.message);
    }

    #[test]
    fn deep_nesting_is_bounded_not_overflowing() {
        let src = format!("{}true{}", "(".repeat(MAX_DEPTH + 50), ")".repeat(MAX_DEPTH + 50));
        let e = parse_err(&src);
        assert_eq!(e.kind, ErrKind::Runtime);
        assert!(e.message.contains("recursion limit"), "{}", e.message);
    }

    #[test]
    fn nesting_cpython_accepts_is_not_rejected() {
        // CPython gives up at nesting depth 199 (measured, default
        // recursionlimit). Anything below that MUST parse here -- the first
        // cut of MAX_DEPTH failed at depth 60 because it counted frames as
        // if they were levels.
        for depth in [60usize, 120, 170, 198] {
            let src = format!("{}true{}", "(".repeat(depth), ")".repeat(depth));
            assert!(parse(&src).is_ok(), "depth {depth} should parse");
        }
    }

    #[test]
    fn or_and_are_left_associative_binary() {
        // Python builds BoolOp(values=[left, right]) pairwise, never n-ary.
        match parse_ok("true or false or true") {
            Node::Or(l, r) => {
                assert!(matches!(*l, Node::Or(_, _)));
                assert_eq!(*r, Node::Bool(true));
            }
            other => panic!("expected Or, got {other:?}"),
        }
    }
}

#[cfg(test)]
mod depth_boundary {
    #![allow(clippy::expect_used)] // test-only: expect_err IS the assertion
    use super::*;

    /// Pin the EXACT frame at which `enter()` rejects.
    ///
    /// This cannot be a differential test, and that is the point. The oracle is
    /// CPython, which raises `RecursionError` at nesting depth ~199 with the
    /// default recursionlimit -- so `NESTING_DEPTHS` is capped at 120 and the
    /// differential can never reach `MAX_DEPTH = 1000`. The ceiling is a
    /// stack-safety backstop with no oracle counterpart, so only a Rust-side
    /// test can hold its boundary.
    ///
    /// It was a surviving mutant that showed the gap: tightening `enter()`'s
    /// `self.depth > MAX_DEPTH` to `>= MAX_DEPTH` -- rejecting one frame early
    /// -- left the differential, property and perf suites all green.
    ///
    /// A `not` chain is the probe because `not_expr` charges exactly ONE frame
    /// per `not` (and folds iteratively, so the Rust stack stays flat). Paren
    /// nesting costs four frames per level and could not resolve a one-frame
    /// shift at all.
    ///
    /// 996 is measured, not derived: `not` chains pay a 4-frame prologue
    /// (`expr` -> `and_expr` -> `not_expr` -> `comparison`). Deriving it from
    /// `MAX_DEPTH` would re-express the comparison under test and let the same
    /// off-by-one slip through both sides.
    const MAX_NOT_CHAIN: usize = 996;

    #[test]
    fn accepts_the_last_frame_inside_the_ceiling() {
        let src = format!("{}true", "not ".repeat(MAX_NOT_CHAIN));
        assert!(
            parse(&src).is_ok(),
            "a {MAX_NOT_CHAIN}-long `not` chain is the deepest input inside the \
             {MAX_DEPTH}-frame ceiling and must parse; rejecting it means \
             `enter()` fires one frame early"
        );
    }

    #[test]
    #[allow(
        clippy::expect_used,
        reason = "test asserts a specific error; expect_err is the clearest \
                  way to express 'this must fail'"
    )]
    fn rejects_the_first_frame_past_the_ceiling() {
        let src = format!("{}true", "not ".repeat(MAX_NOT_CHAIN + 1));
        let err = parse(&src).expect_err("one frame past the ceiling must be rejected");
        assert!(
            format!("{err:?}").contains("recursion limit"),
            "expected the recursion-limit diagnostic, got: {err:?}"
        );
    }
}
