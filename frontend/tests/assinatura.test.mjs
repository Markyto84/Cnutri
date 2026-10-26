import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { capacidadeNovoTraco, CONTRATO_ASSINATURA, normalizarPonto, prepararAssinatura, validarAssinatura } from '../src/modules/assinatura/modelo.js'

const exemplos = JSON.parse(await readFile(new URL('./fixtures/assinatura-v1.json', import.meta.url), 'utf8'))

test('captura e backend usam a mesma versão, dimensões e limites de assinatura', async () => {
  const backend = JSON.parse(await readFile(new URL('../../backend/app/modules/assinatura/contrato.json', import.meta.url), 'utf8'))
  assert.deepEqual(CONTRATO_ASSINATURA, backend)
})

test('exemplos do contrato v1 permanecem válidos e desenhos vazios ou fora da área são recusados', () => {
  for (const { tracos } of exemplos.validas) assert.equal(validarAssinatura(tracos), null)
  for (const { tracos } of exemplos.invalidas) {
    assert.ok(validarAssinatura(tracos))
    assert.throws(() => prepararAssinatura(tracos))
  }
  assert.ok(validarAssinatura([[{ x: NaN, y: 0.2 }, { x: 0.9, y: 0.6 }]]))
  assert.ok(validarAssinatura([[{ x: Infinity, y: 0.2 }, { x: 0.9, y: 0.6 }]]))
})

test('payload é independente da captura e conserva o formato aceito pelas entregas', () => {
  const original = structuredClone(exemplos.validas[0].tracos)
  const payload = prepararAssinatura(original)
  assert.deepEqual(payload, exemplos.validas[0])
  original[0][0].x = 0.9
  original.push([{ x: 0.1, y: 0.1 }, { x: 0.9, y: 0.9 }])
  assert.equal(payload.tracos[0][0].x, 0.1)
  assert.equal(payload.tracos.length, 1)
})

test('coordenadas conservam a posição em quadros de desktop e celular e são limitadas à área', () => {
  assert.deepEqual(normalizarPonto(260, 145, { left: 10, top: 20, width: 1000, height: 500 }), { x: 0.25, y: 0.25 })
  assert.deepEqual(normalizarPonto(90, 60, { left: 10, top: 20, width: 320, height: 160 }), { x: 0.25, y: 0.25 })
  assert.deepEqual(normalizarPonto(-20, 800, { left: 10, top: 20, width: 320, height: 160 }), { x: 0, y: 1 })
  assert.equal(normalizarPonto(1, 1, { left: 0, top: 0, width: 0, height: 100 }), null)
})

test('a captura interrompe novos traços antes de exceder os limites do comprovante', () => {
  const traco = (n) => Array.from({ length: n }, (_, i) => ({ x: i % 2 ? 0.8 : 0.2, y: 0.5 }))
  const limite = Array.from({ length: 5 }, () => traco(1500))
  assert.equal(capacidadeNovoTraco(limite), 500)
  limite.push(traco(500))
  assert.equal(validarAssinatura(limite), null)
  assert.equal(capacidadeNovoTraco(limite), 0)
  limite[5].push({ x: 0.3, y: 0.7 })
  assert.ok(validarAssinatura(limite))
  assert.equal(capacidadeNovoTraco(Array.from({ length: 40 }, () => traco(2))), 0)
  assert.ok(validarAssinatura(Array.from({ length: 41 }, () => traco(2))))
  assert.ok(validarAssinatura([traco(1501)]))
})
