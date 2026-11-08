import {display, stringify} from './json.js';
import {ApiError} from './api.js';

export const answerText = answer => ({yes:'Да',no:'Нет',na:'N/A — не применимо',scale:display(answer.value)}[answer.answer] ?? 'Не выбран');
export const originText = value => ({model:'Оценка ИИ',manual:'Ручная оценка'}[value] ?? value);
export const reviewText = value => ({evaluated:'Оценено',appealed:'Есть апелляция',reviewed:'Проверено',open:'Открыта',resolved:'Рассмотрена'}[value] ?? value);
export const assessmentChanged = evaluation => stringify(evaluation.original_answers)!==stringify(evaluation.final_answers)
  || stringify(evaluation.original_score)!==stringify(evaluation.final_score);
export const aiStatusText = state => state.reason ? new ApiError(0,state.reason).message : !state.ml_configured ? 'ИИ не настроен на сервере' :
  !state.ml_reachable ? 'Нет связи с ML-сервисом' : !state.ml_ready ? 'ML-сервис не готов к оценке' : 'ML-сервис готов; доступ к выбранным данным проверяется отдельно';
