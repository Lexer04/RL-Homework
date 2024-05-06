import os
import random
import gymnasium as gym
import pylab
import numpy as np
from collections import deque
import tensorflow as tf
from tensorflow.keras.models import Model, load_model
from tensorflow.keras.layers import Input, Dense
from tensorflow.keras.optimizers import Adam, RMSprop


def OurModel(input_shape, action_space):
    X_input = Input(input_shape)
    X = X_input

    # 'Dense' is the basic form of a neural network layer
    # Input Layer of state size(4) and Hidden Layer with 512 nodes
    X = Dense(512, input_shape=input_shape, activation="relu", kernel_initializer='he_uniform')(X)

    # Hidden layer with 256 nodes
    X = Dense(256, activation="relu", kernel_initializer='he_uniform')(X)
    
    # Hidden layer with 64 nodes
    X = Dense(64, activation="relu", kernel_initializer='he_uniform')(X)

    # Output Layer with # of actions: 2 nodes (left, right)
    X = Dense(action_space, activation="linear", kernel_initializer='he_uniform')(X)

    model = Model(inputs = X_input, outputs = X)
    model.compile(loss="mean_squared_error", optimizer=RMSprop(learning_rate=0.00025, rho=0.95, epsilon=0.01), metrics=["accuracy"])

    model.summary()
    return model

class DQNAgent:
    def __init__(self, env_name):
        self.env_name = env_name       
        self.env = gym.make(env_name)
        self.env.reset(seed=0)  
        # by default, CartPole-v1 has max episode steps = 500
        self.env._max_episode_steps = 4000
        self.state_size = self.env.observation_space.shape[0]
        self.action_size = self.env.action_space.n

        self.EPISODES = 2000
        self.memory = deque(maxlen=2000)
        
        self.gamma = 0.95    # discount rate
        self.epsilon = 1.0  # exploration rate
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.999
        self.batch_size = 32
        self.train_start = 1000

        # defining model parameters
        self.ddqn = True
        self.Soft_Update = False

        self.TAU = 0.1 # target network soft update hyperparameter

        self.Save_Path = 'Models'
        self.scores, self.episodes, self.average = [], [], []
        
        if self.ddqn:
            print("----------Triple DQN--------")
            self.Model_name = os.path.join(self.Save_Path,"TDQN_"+self.env_name+".h5")
        
        # create main model
        self.model = OurModel(input_shape=(self.state_size,), action_space = self.action_size)
        self.target_model1 = OurModel(input_shape=(self.state_size,), action_space = self.action_size)
        self.target_model2 = OurModel(input_shape=(self.state_size,), action_space = self.action_size)

    # after some time interval update the target model to be same with model
    def update_target_model(self):
        if not self.Soft_Update and self.ddqn:
            self.target_model1.set_weights(self.model.get_weights())
            self.target_model2.set_weights(self.model.get_weights())
            return
        if self.Soft_Update and self.ddqn:
            q_model_theta = self.model.get_weights()
            target_model1_theta = self.target_model1.get_weights()
            target_model2_theta = self.target_model2.get_weights()
            counter = 0
            for q_weight, target_weight1, target_weight2 in zip(q_model_theta, target_model1_theta, target_model2_theta):
                target_weight1 = target_weight1 * (1-self.TAU) + q_weight * self.TAU
                target_weight2 = target_weight2 * (1-self.TAU) + q_weight * self.TAU
                target_model1_theta[counter] = target_weight1
                target_model2_theta[counter] = target_weight2
                counter += 1
            self.target_model1.set_weights(target_model1_theta)
            self.target_model2.set_weights(target_model2_theta)

    def remember(self, state, action, reward, next_state, done):
        self.memory.append((state, action, reward, next_state, done))
        if len(self.memory) > self.train_start:
            if self.epsilon > self.epsilon_min:
                self.epsilon *= self.epsilon_decay

    def act(self, state):
        if np.random.random() <= self.epsilon:
            return random.randrange(self.action_size)
        else:
            return np.argmax(self.model.predict(state))

    def replay(self):
        if len(self.memory) < self.train_start:
            return
        # Randomly sample minibatch from the memory
        minibatch = random.sample(self.memory, min(self.batch_size, len(self.memory)))

        state = np.zeros((self.batch_size, self.state_size))
        next_state = np.zeros((self.batch_size, self.state_size))
        action, reward, done = [], [], []

        # do this before prediction
        # for speedup, this could be done on the tensor level
        # but easier to understand using a loop
        for i in range(self.batch_size):
            state[i] = minibatch[i][0]
            action.append(minibatch[i][1])
            reward.append(minibatch[i][2])
            next_state[i] = minibatch[i][3]
            done.append(minibatch[i][4])

        # do batch prediction to save speed
        target1 = self.model.predict(state)
        target2 = self.model.predict(state)
        target_next1 = self.model.predict(next_state)
        target_next2 = self.model.predict(next_state)
        target_val1 = self.target_model1.predict(next_state)
        target_val2 = self.target_model2.predict(next_state)

        for i in range(len(minibatch)):
            # correction on the Q value for the action used
            if done[i]:
                target1[i][action[i]] = reward[i]
                target2[i][action[i]] = reward[i]
            else:
                if self.ddqn: # Double - DQN
                    # current Q Network selects the action
                    # a'_max = argmax_a' Q(s', a')
                    a1 = np.argmax(target_next1[i])
                    a2 = np.argmax(target_next2[i])
                    # target Q Network evaluates the action
                    # Q_max = Q_target(s', a'_max)
                    target1[i][action[i]] = reward[i] + self.gamma * (target_val1[i][a1])   
                    target2[i][action[i]] = reward[i] + self.gamma * (target_val2[i][a2])   
                       
                else: # Standard - DQN
                    # DQN chooses the max Q value among next actions
                    # selection and evaluation of action is on the target Q Network
                    # Q_max = max_a' Q_target(s', a')
                    target1[i][action[i]] = reward[i] + self.gamma * (np.amax(target_val1[i]))
                    target2[i][action[i]] = reward[i] + self.gamma * (np.amax(target_val2[i]))

        # Train the Neural Network with batches
        # Model = Q1
        # target_model = Q2
        # 
        self.model.fit(state, target1, batch_size=self.batch_size, verbose=1)
        self.model.fit(state, target2, batch_size=self.batch_size, verbose=1)


    def load(self, name):
        self.model = load_model(name)

    def save(self, name):
        self.model.save(name)

    pylab.figure(figsize=(18, 9))
    def PlotModel(self, score, episode):
        self.scores.append(score)
        self.episodes.append(episode)
        self.average.append(sum(self.scores) / len(self.scores))
        pylab.plot(self.episodes, self.average, 'r')
        pylab.plot(self.episodes, self.scores, 'b')
        pylab.ylabel('Score', fontsize=18)
        pylab.xlabel('Steps', fontsize=18)
        dqn = 'TDQN_'
        softupdate = ''
        if self.ddqn:
            dqn = 'TDQN_'
        if self.Soft_Update:
            softupdate = '_soft'
        try:
            pylab.savefig(dqn+self.env_name+softupdate+".png")
        except OSError:
            pass

        return str(self.average[-1])[:5]
    
    def run(self):
        for e in range(self.EPISODES):
            state = self.env.reset()
            #print("State type:", type(state))
            #print("State:", state)
            state = [np.array(s) for s in state][0]  # Convert each element of the tuple to a numpy array
            state = np.array(state).reshape(1, -1)
            done = False
            i = 0
            while not done:
                action = self.act(state)
            
                result = self.env.step(action)
                next_state, reward, done, _ = result[:4]  # Extracting the necessary values
                
                next_state = [np.array(s) for s in next_state]  # Convert each element of the tuple to a numpy array
                next_state = np.array(next_state).reshape(1, -1)
                if not done or i == self.env._max_episode_steps - 1:
                    reward = reward
                else:
                    reward = -100
                self.remember(state, action, reward, next_state, done)
                state = next_state
                i += 1
                if done:
                    self.update_target_model()
                    average = self.PlotModel(i, e)
                    print("episode: {}/{}, score: {}, e: {:.2}, average: {}".format(e, self.EPISODES, i, self.epsilon, average))
                    if i == self.env._max_episode_steps:
                        print("Saving trained model as cartpole-tdqn.h5")
                        self.save("cartpole-tdqn.h5")
                        break
                self.replay()


    def test(self):
        self.load("cartpole-ddqn.h5")
        for e in range(self.EPISODES):
            state = self.env.reset()
            
            state = np.reshape(state, [1, self.state_size])
            done = False
            i = 0
            while not done:
                self.env.render()
                action = np.argmax(self.model.predict(state))
                next_state, reward, done, _ = self.env.step(action)
                state = np.reshape(next_state, [1, self.state_size])
                i += 1
                if done:
                    print("episode: {}/{}, score: {}".format(e, self.EPISODES, i))
                    break

if __name__ == "__main__":
    env_name = 'CartPole-v1'
    agent = DQNAgent(env_name)
    agent.run()
    #agent.test()