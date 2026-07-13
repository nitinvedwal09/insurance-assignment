import random
from dataclasses import dataclass

from app import storage

EPSILON = 0.2


def context_key(decision_point: str, context: str) -> str:
    return f"{decision_point}::{context}"


@dataclass
class Choice:
    decision_point: str
    context: str
    action: str


class ContextualBandit:

    def choose(self, decision_point: str, context: str, actions: list[str]) -> Choice:
        key_prefix = context_key(decision_point, context)
        if random.random() < EPSILON:
            action = random.choice(actions)
        else:
            stats = {action: storage.get_arm_stats(f"{key_prefix}::{action}") for action in actions}
            action = max(actions, key=lambda a: stats[a][1] / stats[a][0] if stats[a][0] else 0.0)
        return Choice(decision_point=decision_point, context=context, action=action)

    def record_reward(self, choices: list[Choice], reward: float) -> None:
        for choice in choices:
            key = f"{context_key(choice.decision_point, choice.context)}::{choice.action}"
            storage.update_arm(key, reward)


bandit = ContextualBandit()
