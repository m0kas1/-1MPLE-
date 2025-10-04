import numpy as np
import scipy.stats
import time

def TimeByOnePerson(sample, M):
    n = len(sample)  # длина выборки
    df = n - 1  # степени свободы

    mean_x = np.mean(sample)  # выборочное среднее
    sd = np.std(sample, ddof=1)  # стандартное отклонение выборки
    SE = sd / np.sqrt(n)  # стандартная ошибка генеральной выборки
    t = (mean_x - M) / SE  # t-статистика
    p_value = 2 * (1 - scipy.stats.t.cdf(abs(t), df))  # насколько мы уверены в гипотезе H0
    if p_value >= 0.0002:
        return M
    return round(mean_x, 1)

# из бд:
M = 10  # условное время которое мы берем для определенной активности
sample = np.round(np.random.uniform(6, 10, size=15), 1)
#

while True:
    sample = np.round(np.random.uniform(6, 10, size=7), 1)
    print(TimeByOnePerson(sample, M), sample)
    time.sleep(0.2)