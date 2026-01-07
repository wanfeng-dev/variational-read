<script setup lang="ts">
import { ref } from 'vue'
import dayjs from 'dayjs'

const emit = defineEmits<{
  runBacktest: [params: { start: string; end: string }]
  runWalkForward: [params: {
    start: string
    end: string
    trainWindow: number
    testWindow: number
    stepSize: number
  }]
}>()

// 默认值：过去 7 天
const defaultEnd = dayjs().format('YYYY-MM-DDTHH:mm')
const defaultStart = dayjs().subtract(7, 'day').format('YYYY-MM-DDTHH:mm')

const form = ref({
  start: defaultStart,
  end: defaultEnd,
  trainWindow: 7,
  testWindow: 1,
  stepSize: 1,
})

const loading = ref(false)
const mode = ref<'backtest' | 'walkforward'>('backtest')

function handleSubmit() {
  loading.value = true
  if (mode.value === 'backtest') {
    emit('runBacktest', {
      start: new Date(form.value.start).toISOString(),
      end: new Date(form.value.end).toISOString(),
    })
  } else {
    emit('runWalkForward', {
      start: new Date(form.value.start).toISOString(),
      end: new Date(form.value.end).toISOString(),
      trainWindow: form.value.trainWindow,
      testWindow: form.value.testWindow,
      stepSize: form.value.stepSize,
    })
  }
}

function setLoading(val: boolean) {
  loading.value = val
}

defineExpose({ setLoading })
</script>

<template>
  <div class="backtest-form">
    <h3>回测配置</h3>

    <div class="form-group">
      <label>数据范围</label>
      <div class="date-range">
        <input type="datetime-local" v-model="form.start" />
        <span>至</span>
        <input type="datetime-local" v-model="form.end" />
      </div>
    </div>

    <div class="form-group">
      <label>回测类型</label>
      <div class="mode-selector">
        <button
          :class="{ active: mode === 'backtest' }"
          @click="mode = 'backtest'"
        >
          普通回测
        </button>
        <button
          :class="{ active: mode === 'walkforward' }"
          @click="mode = 'walkforward'"
        >
          走步验证
        </button>
      </div>
    </div>

    <template v-if="mode === 'walkforward'">
      <div class="form-row">
        <div class="form-group">
          <label>训练窗口（天）</label>
          <input type="number" v-model.number="form.trainWindow" min="1" max="30" />
        </div>
        <div class="form-group">
          <label>测试窗口（天）</label>
          <input type="number" v-model.number="form.testWindow" min="1" max="7" />
        </div>
        <div class="form-group">
          <label>步进（天）</label>
          <input type="number" v-model.number="form.stepSize" min="1" max="7" />
        </div>
      </div>
    </template>

    <button
      class="btn-submit"
      :disabled="loading"
      @click="handleSubmit"
    >
      {{ loading ? '运行中...' : mode === 'backtest' ? '运行回测' : '运行走步验证' }}
    </button>
  </div>
</template>

<style scoped>
.backtest-form {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  padding: 20px;
  border: 1px solid var(--border-card);
}

h3 {
  margin: 0 0 20px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.form-group {
  margin-bottom: 18px;
}

.form-group label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.form-group input {
  width: 100%;
  padding: 12px 14px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-card);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 14px;
  transition: border-color 0.2s ease;
}

.form-group input:focus {
  outline: none;
  border-color: var(--accent-blue);
}

.form-group input::placeholder {
  color: var(--text-muted);
}

.date-range {
  display: flex;
  align-items: center;
  gap: 12px;
}

.date-range input {
  flex: 1;
}

.date-range span {
  color: var(--text-muted);
}

.mode-selector {
  display: flex;
  gap: 8px;
}

.mode-selector button {
  flex: 1;
  padding: 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-card);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.mode-selector button:hover:not(.active) {
  border-color: var(--border-accent);
  color: var(--text-primary);
}

.mode-selector button.active {
  background: var(--accent-blue);
  border-color: var(--accent-blue);
  color: #fff;
}

.form-row {
  display: flex;
  gap: 12px;
}

.form-row .form-group {
  flex: 1;
}

.btn-submit {
  width: 100%;
  padding: 14px;
  background: var(--accent-blue);
  border: none;
  border-radius: var(--radius-sm);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-submit:hover:not(:disabled) {
  background: #3d8ee6;
}

.btn-submit:active:not(:disabled) {
  transform: scale(0.98);
}

.btn-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@media (max-width: 768px) {
  .backtest-form {
    padding: 16px;
  }
  
  h3 {
    font-size: 15px;
  }
  
  .form-row {
    flex-direction: column;
  }
}
</style>
