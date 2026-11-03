import assert from 'node:assert/strict'
import test from 'node:test'
import { agoraBrasilia, dataEntregaISO, prepararFotoComprovante } from '../src/services/fotoComprovante.js'

test('lançamento usa o horário escrito em Brasília e não o fuso do dispositivo', () => {
  assert.equal(dataEntregaISO('2026-11-03T12:34'), '2026-11-03T12:34:00-03:00')
  assert.equal(agoraBrasilia(new Date('2026-11-03T15:34:59Z')), '2026-11-03T12:34')
  for (const data of ['', '2026-02-30T12:00', '2026-13-01T12:00', '2026-11-03T25:10', '2026-11-03T12:00Z', '2026-11-03']) assert.equal(dataEntregaISO(data), '')
})

test('foto recusa arquivo vazio, formato incompatível e tamanho antes de decodificar', async () => {
  for (const arquivo of [null, {size:0,type:'image/jpeg'}, {size:12*1024*1024+1,type:'image/jpeg'}, {size:100,type:'image/svg+xml'}, {size:100,type:'image/heic'}]) {
    await assert.rejects(prepararFotoComprovante(arquivo))
  }
})
